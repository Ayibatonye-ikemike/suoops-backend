"""Marketing Campaign Service for WhatsApp outreach.

Sends marketing templates to users for:
- Activation: Users who signed up but haven't created invoices
- Win-back: Users who haven't been active recently (7+ days)
- Low Balance: Users running low on invoice credits
- Pro Upgrade: Free/Starter users to convert to Pro
- Invoice Pack Promo: Users with zero balance
- First Invoice Followup: Celebrate first invoice + upsell

IMPORTANT: WhatsApp Marketing templates require user opt-in within 24 hours
or users who have previously interacted with your business.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bot.whatsapp_client import WhatsAppClient
from app.core.config import settings
from app.models import models
from app.models.models import SubscriptionPlan

# Aliases for cleaner code
User = models.User
Invoice = models.Invoice

logger = logging.getLogger(__name__)


class CampaignType(str, Enum):
    """Available marketing campaign types."""
    ACTIVATION_WELCOME = "activation_welcome"
    WIN_BACK_REMINDER = "win_back_reminder"
    LOW_BALANCE_REMINDER = "low_balance_reminder"
    # New conversion campaigns
    PRO_UPGRADE = "pro_upgrade"
    INVOICE_PACK_PROMO = "invoice_pack_promo"
    FIRST_INVOICE_FOLLOWUP = "first_invoice_followup"


# Template configurations
# NOTE: You'll need to create these templates in Meta Business Suite first
CAMPAIGN_TEMPLATES = {
    CampaignType.ACTIVATION_WELCOME: {
        "template_name": "activation_welcome",
        "language": "en",
        "description": "Users who signed up but haven't created invoices (3+ days)",
        "params": ["name"],  # {{1}} = user name
        "goal": "Activate new users",
    },
    CampaignType.WIN_BACK_REMINDER: {
        "template_name": "win_back_reminder",
        "language": "en",
        "description": "Active users who haven't used SuoOps in 7+ days",
        "params": ["name"],  # {{1}} = user name
        "goal": "Re-engage inactive users",
    },
    CampaignType.LOW_BALANCE_REMINDER: {
        "template_name": "low_balance_reminder",
        "language": "en",
        "description": "Users with 5 or fewer invoices remaining",
        "params": ["name", "remaining_invoices"],  # {{1}} = name, {{2}} = remaining count
        "goal": "Drive invoice pack purchases",
    },
    CampaignType.PRO_UPGRADE: {
        "template_name": "pro_upgrade",
        "language": "en",
        "description": "Free/Starter users who've created 5+ invoices - ready to upgrade",
        "params": ["name", "invoice_count"],  # {{1}} = name, {{2}} = invoice count
        "goal": "Convert to Pro subscription (₦5,000/month)",
    },
    CampaignType.INVOICE_PACK_PROMO: {
        "template_name": "invoice_pack_promo",
        "language": "en",
        "description": "Users with zero invoice balance who need to buy packs",
        "params": ["name"],  # {{1}} = user name
        "goal": "Drive invoice pack purchases (₦2,500 for 100)",
    },
    CampaignType.FIRST_INVOICE_FOLLOWUP: {
        "template_name": "first_invoice_followup",
        "language": "en",
        "description": "Users who created their first invoice in the last 24-72 hours",
        "params": ["name"],  # {{1}} = user name
        "goal": "Congratulate + promote Pro features",
    },
}


class MarketingCampaignService:
    """Service to send marketing campaigns via WhatsApp."""

    def __init__(self, db: Session):
        self.db = db
        self.client = WhatsAppClient(settings.WHATSAPP_API_KEY or "")

    def get_activation_candidates(self, days_since_signup: int = 3, limit: int = 100) -> list[User]:
        """Get users who signed up but never created an invoice.
        
        Args:
            days_since_signup: Only include users who signed up at least this many days ago
            limit: Maximum users to return
            
        Raises:
            Exception: If database query fails
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_since_signup)
            
            # Users with phone, signed up before cutoff, with zero invoices
            stmt = (
                select(User)
                .where(User.phone.isnot(None))
                .where(User.phone_verified == True)  # noqa: E712
                .where(User.created_at <= cutoff_date)
                .where(
                    ~User.id.in_(
                        select(Invoice.issuer_id).where(Invoice.issuer_id.isnot(None)).distinct()
                    )
                )
                .limit(limit)
            )
            
            result = list(self.db.execute(stmt).scalars().all())
            logger.info("[CAMPAIGN] Found %d activation candidates", len(result))
            return result
        except Exception as e:
            logger.exception("[CAMPAIGN] Failed to fetch activation candidates: %s", e)
            raise

    def get_winback_candidates(self, inactive_days: int = 7, limit: int = 100) -> list[User]:
        """Get users who haven't created invoices recently.
        
        Args:
            inactive_days: Consider users inactive if no invoice in this many days (default: 7)
            limit: Maximum users to return
            
        Raises:
            Exception: If database query fails
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=inactive_days)
            
            # Users with phone who have created invoices before, but none recently
            stmt = (
                select(User)
                .where(User.phone.isnot(None))
                .where(User.phone_verified == True)  # noqa: E712
                .where(
                    User.id.in_(
                        select(Invoice.issuer_id)
                        .where(Invoice.issuer_id.isnot(None))
                        .where(Invoice.created_at < cutoff_date)
                        .distinct()
                    )
                )
                .where(
                    ~User.id.in_(
                        select(Invoice.issuer_id)
                        .where(Invoice.issuer_id.isnot(None))
                        .where(Invoice.created_at >= cutoff_date)
                        .distinct()
                    )
                )
                .limit(limit)
            )
            
            result = list(self.db.execute(stmt).scalars().all())
            logger.info("[CAMPAIGN] Found %d winback candidates", len(result))
            return result
        except Exception as e:
            logger.exception("[CAMPAIGN] Failed to fetch winback candidates: %s", e)
            raise

    def get_low_balance_candidates(self, threshold: int = 5, limit: int = 100) -> list[tuple[User, int]]:
        """Get users with low invoice balance.
        
        Args:
            threshold: Users with this many or fewer invoices remaining
            limit: Maximum users to return
            
        Returns:
            List of (User, remaining_count) tuples
            
        Raises:
            Exception: If database query fails
        """
        try:
            # Get users with invoice balance tracking
            # This assumes you have invoice_balance on User model
            stmt = (
                select(User)
                .where(User.phone.isnot(None))
                .where(User.phone_verified == True)  # noqa: E712
                .where(User.invoice_balance <= threshold)
                .where(User.invoice_balance > 0)  # Don't notify users with 0 balance
                .limit(limit)
            )
            
            users = list(self.db.execute(stmt).scalars().all())
            logger.info("[CAMPAIGN] Found %d low balance candidates", len(users))
            return [(user, user.invoice_balance) for user in users]
        except Exception as e:
            logger.exception("[CAMPAIGN] Failed to fetch low balance candidates: %s", e)
            raise

    def get_pro_upgrade_candidates(self, min_invoices: int = 5, limit: int = 100) -> list[tuple[User, int]]:
        """Get Free/Starter users who've used the platform enough to consider Pro.
        
        Target: Users who have created at least min_invoices invoices but are still
        on Free/Starter plan - they're clearly using the product and could benefit from Pro.
        
        Args:
            min_invoices: Minimum invoices created to qualify (default: 5)
            limit: Maximum users to return
            
        Returns:
            List of (User, invoice_count) tuples
            
        Raises:
            Exception: If database query fails
        """
        try:
            # Subquery to count invoices per user
            invoice_count_subq = (
                select(Invoice.issuer_id, func.count(Invoice.id).label("invoice_count"))
                .where(Invoice.issuer_id.isnot(None))
                .group_by(Invoice.issuer_id)
                .having(func.count(Invoice.id) >= min_invoices)
                .subquery()
            )
            
            # Users on Free/Starter with enough invoices
            stmt = (
                select(User, invoice_count_subq.c.invoice_count)
                .join(invoice_count_subq, User.id == invoice_count_subq.c.issuer_id)
                .where(User.phone.isnot(None))
                .where(User.phone_verified == True)  # noqa: E712
                .where(User.plan.in_([SubscriptionPlan.FREE, SubscriptionPlan.STARTER]))
                .order_by(invoice_count_subq.c.invoice_count.desc())
                .limit(limit)
            )
            
            results = self.db.execute(stmt).all()
            logger.info("[CAMPAIGN] Found %d pro upgrade candidates", len(results))
            return [(row[0], row[1]) for row in results]
        except Exception as e:
            logger.exception("[CAMPAIGN] Failed to fetch pro upgrade candidates: %s", e)
            raise

    def get_zero_balance_candidates(self, limit: int = 100) -> list[User]:
        """Get users with zero invoice balance who need to buy packs.
        
        These users have run out of invoices and need to purchase more.
        Great opportunity to promote invoice packs or Pro subscription.
        
        Args:
            limit: Maximum users to return
            
        Raises:
            Exception: If database query fails
        """
        try:
            stmt = (
                select(User)
                .where(User.phone.isnot(None))
                .where(User.phone_verified == True)  # noqa: E712
                .where(User.invoice_balance == 0)
                # Only target users who've actually used the platform
                .where(
                    User.id.in_(
                        select(Invoice.issuer_id).where(Invoice.issuer_id.isnot(None)).distinct()
                    )
                )
                .limit(limit)
            )
            
            result = list(self.db.execute(stmt).scalars().all())
            logger.info("[CAMPAIGN] Found %d zero balance candidates", len(result))
            return result
        except Exception as e:
            logger.exception("[CAMPAIGN] Failed to fetch zero balance candidates: %s", e)
            raise

    def get_first_invoice_candidates(self, hours_ago_min: int = 24, hours_ago_max: int = 72, limit: int = 100) -> list[User]:
        """Get users who created their first invoice recently.
        
        Target the "aha moment" - users who just created their first invoice
        are excited and receptive to learning about more features.
        
        Args:
            hours_ago_min: Minimum hours since first invoice (default: 24)
            hours_ago_max: Maximum hours since first invoice (default: 72)
            limit: Maximum users to return
            
        Raises:
            Exception: If database query fails
        """
        try:
            now = datetime.now(timezone.utc)
            min_time = now - timedelta(hours=hours_ago_max)
            max_time = now - timedelta(hours=hours_ago_min)
            
            # Subquery to get each user's first invoice timestamp
            first_invoice_subq = (
                select(
                    Invoice.issuer_id,
                    func.min(Invoice.created_at).label("first_invoice_at"),
                    func.count(Invoice.id).label("invoice_count")
                )
                .where(Invoice.issuer_id.isnot(None))
                .group_by(Invoice.issuer_id)
                .having(func.count(Invoice.id) == 1)  # Only first invoice
                .subquery()
            )
            
            # Users whose first (and only) invoice was created in the time window
            stmt = (
                select(User)
                .join(first_invoice_subq, User.id == first_invoice_subq.c.issuer_id)
                .where(User.phone.isnot(None))
                .where(User.phone_verified == True)  # noqa: E712
                .where(first_invoice_subq.c.first_invoice_at >= min_time)
                .where(first_invoice_subq.c.first_invoice_at <= max_time)
                .limit(limit)
            )
            
            result = list(self.db.execute(stmt).scalars().all())
            logger.info("[CAMPAIGN] Found %d first invoice candidates", len(result))
            return result
        except Exception as e:
            logger.exception("[CAMPAIGN] Failed to fetch first invoice candidates: %s", e)
            raise

    def send_campaign(
        self,
        campaign_type: CampaignType,
        dry_run: bool = True,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Send a marketing campaign to eligible users.
        
        Args:
            campaign_type: Type of campaign to send
            dry_run: If True, only simulate sending (default: True for safety)
            limit: Maximum messages to send (capped at 100 for rate limiting)
            
        Returns:
            Summary of campaign results
        """
        # Cap limit to prevent rate limiting issues
        limit = min(limit, 100)
        
        config = CAMPAIGN_TEMPLATES.get(campaign_type)
        if not config:
            logger.error("[CAMPAIGN] Unknown campaign type: %s", campaign_type)
            return {
                "campaign": campaign_type.value if hasattr(campaign_type, "value") else str(campaign_type),
                "template": "unknown",
                "dry_run": dry_run,
                "candidates": 0,
                "sent": 0,
                "failed": 0,
                "skipped": 0,
                "error": f"Unknown campaign type: {campaign_type}",
                "details": [],
            }
        
        template_name = config["template_name"]
        language = config["language"]
        
        results: dict[str, Any] = {
            "campaign": campaign_type.value,
            "template": template_name,
            "dry_run": dry_run,
            "candidates": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
            "details": [],
        }
        
        # Get candidates with error handling
        try:
            if campaign_type == CampaignType.ACTIVATION_WELCOME:
                candidates = [(u, None) for u in self.get_activation_candidates(limit=limit)]
            elif campaign_type == CampaignType.WIN_BACK_REMINDER:
                candidates = [(u, None) for u in self.get_winback_candidates(limit=limit)]
            elif campaign_type == CampaignType.LOW_BALANCE_REMINDER:
                candidates = self.get_low_balance_candidates(limit=limit)
            elif campaign_type == CampaignType.PRO_UPGRADE:
                candidates = self.get_pro_upgrade_candidates(limit=limit)
            elif campaign_type == CampaignType.INVOICE_PACK_PROMO:
                candidates = [(u, None) for u in self.get_zero_balance_candidates(limit=limit)]
            elif campaign_type == CampaignType.FIRST_INVOICE_FOLLOWUP:
                candidates = [(u, None) for u in self.get_first_invoice_candidates(limit=limit)]
            else:
                logger.error("[CAMPAIGN] Unknown campaign type: %s", campaign_type)
                results["error"] = f"Unknown campaign type: {campaign_type}"
                return results
        except Exception as e:
            logger.exception("[CAMPAIGN] Failed to fetch candidates for %s", campaign_type.value)
            results["error"] = f"Database error fetching candidates: {str(e)}"
            return results
        
        results["candidates"] = len(candidates)
        
        if not candidates:
            logger.info("[CAMPAIGN] No candidates found for %s", campaign_type.value)
            results["message"] = "No eligible users found for this campaign"
            return results
        
        # Rate limiting: 2 messages per second max
        import time
        rate_limit_delay = 0.5  # seconds between messages
        
        for idx, (user, extra_data) in enumerate(candidates):
            # Skip users without phone numbers
            if not user.phone:
                results["skipped"] += 1
                results["details"].append({
                    "user_id": user.id,
                    "name": user.name or "Unknown",
                    "phone": "N/A",
                    "status": "skipped",
                    "reason": "No phone number",
                })
                continue
            
            # Validate phone format (must start with + or be numeric)
            phone = user.phone.strip()
            if not (phone.startswith("+") or phone.isdigit()):
                results["skipped"] += 1
                results["details"].append({
                    "user_id": user.id,
                    "name": user.name or "Unknown",
                    "phone": phone[-4:].rjust(len(phone), "*"),
                    "status": "skipped",
                    "reason": "Invalid phone format",
                })
                continue
            
            user_name = user.name or "there"
            
            # Build template components based on campaign type
            try:
                if campaign_type == CampaignType.LOW_BALANCE_REMINDER:
                    # {{1}} = name, {{2}} = remaining count
                    components = [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": user_name},
                                {"type": "text", "text": str(extra_data or 0)},
                            ],
                        }
                    ]
                elif campaign_type == CampaignType.PRO_UPGRADE:
                    # {{1}} = name, {{2}} = invoice count
                    components = [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": user_name},
                                {"type": "text", "text": str(extra_data or 0)},
                            ],
                        }
                    ]
                else:
                    # activation_welcome, win_back_reminder, invoice_pack_promo, 
                    # first_invoice_followup - all have 1 param (name)
                    components = [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": user_name},
                            ],
                        }
                    ]
            except Exception as e:
                logger.error("[CAMPAIGN] Failed to build components for user %s: %s", user.id, e)
                results["failed"] += 1
                results["details"].append({
                    "user_id": user.id,
                    "name": user_name,
                    "phone": phone[-4:].rjust(len(phone), "*"),
                    "status": "failed",
                    "reason": f"Component build error: {str(e)}",
                })
                continue
            
            if dry_run:
                logger.info(
                    "[CAMPAIGN][DRY_RUN] Would send %s to %s (%s)",
                    template_name, user_name, phone
                )
                results["details"].append({
                    "user_id": user.id,
                    "name": user_name,
                    "phone": phone[-4:].rjust(len(phone), "*"),  # Mask phone
                    "status": "dry_run",
                })
                results["sent"] += 1
            else:
                # Actual send with error handling
                try:
                    success = self.client.send_template(
                        to=phone,
                        template_name=template_name,
                        language=language,
                        components=components,
                    )
                    
                    if success:
                        results["sent"] += 1
                        results["details"].append({
                            "user_id": user.id,
                            "name": user_name,
                            "phone": phone[-4:].rjust(len(phone), "*"),
                            "status": "sent",
                        })
                        logger.info("[CAMPAIGN] Sent %s to %s", template_name, user_name)
                    else:
                        results["failed"] += 1
                        results["details"].append({
                            "user_id": user.id,
                            "name": user_name,
                            "phone": phone[-4:].rjust(len(phone), "*"),
                            "status": "failed",
                            "reason": "WhatsApp API returned failure",
                        })
                        results["errors"].append(f"Failed to send to user {user.id}")
                        logger.warning("[CAMPAIGN] Failed to send %s to %s", template_name, user_name)
                except Exception as e:
                    results["failed"] += 1
                    error_msg = str(e)
                    results["details"].append({
                        "user_id": user.id,
                        "name": user_name,
                        "phone": phone[-4:].rjust(len(phone), "*"),
                        "status": "failed",
                        "reason": error_msg[:100],  # Truncate long errors
                    })
                    results["errors"].append(f"User {user.id}: {error_msg[:50]}")
                    logger.exception("[CAMPAIGN] Exception sending to %s: %s", user_name, e)
                
                # Rate limit between actual sends (not dry runs)
                if idx < len(candidates) - 1:
                    time.sleep(rate_limit_delay)
        
        # Summary log
        logger.info(
            "[CAMPAIGN] %s complete: %d sent, %d failed, %d skipped out of %d candidates",
            campaign_type.value, results["sent"], results["failed"], results["skipped"], results["candidates"]
        )
        
        # Add summary message
        if results["failed"] > 0:
            results["message"] = f"Campaign completed with {results['failed']} failures. Check errors for details."
        else:
            results["message"] = f"Campaign completed successfully. {results['sent']} messages sent."
        
        return results

    def send_to_single_user(
        self,
        phone: str,
        campaign_type: CampaignType,
        user_name: str = "there",
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a marketing template to a single user.
        
        Args:
            phone: User's phone number
            campaign_type: Type of campaign/template to send
            user_name: User's name for personalization
            extra_params: Additional parameters for the template
            
        Returns:
            Dict with success status and details
        """
        result = {
            "success": False,
            "phone": phone[-4:].rjust(len(phone), "*") if phone else "N/A",
            "campaign_type": campaign_type.value,
            "message": "",
            "error": None,
        }
        
        # Validate phone
        if not phone or not phone.strip():
            result["error"] = "Phone number is required"
            result["message"] = "Cannot send: No phone number provided"
            return result
        
        phone = phone.strip()
        if not (phone.startswith("+") or phone.isdigit()):
            result["error"] = "Invalid phone format"
            result["message"] = "Phone must start with + or be numeric"
            return result
        
        # Get template config
        config = CAMPAIGN_TEMPLATES.get(campaign_type)
        if not config:
            result["error"] = f"Unknown campaign type: {campaign_type}"
            result["message"] = "Invalid campaign type specified"
            return result
        
        template_name = config["template_name"]
        language = config["language"]
        
        # Build components
        try:
            if campaign_type in [CampaignType.LOW_BALANCE_REMINDER, CampaignType.PRO_UPGRADE]:
                # These templates have 2 params: {{1}} = name, {{2}} = count
                if campaign_type == CampaignType.LOW_BALANCE_REMINDER:
                    second_param = extra_params.get("remaining_invoices", "5") if extra_params else "5"
                else:  # PRO_UPGRADE
                    second_param = extra_params.get("invoice_count", "10") if extra_params else "10"
                components = [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": user_name},
                            {"type": "text", "text": second_param},
                        ],
                    }
                ]
            else:
                # Single param templates: activation_welcome, win_back_reminder, 
                # invoice_pack_promo, first_invoice_followup
                components = [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": user_name},
                        ],
                    }
                ]
        except Exception as e:
            logger.error("[CAMPAIGN] Failed to build components: %s", e)
            result["error"] = f"Failed to build template components: {str(e)}"
            result["message"] = "Internal error preparing message"
            return result
        
        # Send the template
        try:
            success = self.client.send_template(
                to=phone,
                template_name=template_name,
                language=language,
                components=components,
            )
            
            if success:
                result["success"] = True
                result["message"] = f"Successfully sent {campaign_type.value} template"
                logger.info("[CAMPAIGN] Single send success: %s to %s", template_name, phone[-4:])
            else:
                result["error"] = "WhatsApp API returned failure"
                result["message"] = "Message not sent. Please check the phone number and try again."
                logger.warning("[CAMPAIGN] Single send failed: %s to %s", template_name, phone[-4:])
        except Exception as e:
            error_msg = str(e)
            result["error"] = error_msg[:200]  # Truncate long errors
            result["message"] = "Failed to send message. Please try again later."
            logger.exception("[CAMPAIGN] Exception in single send: %s", e)
        
        return result
