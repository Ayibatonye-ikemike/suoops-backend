"""Marketing Campaign Service for WhatsApp outreach.

Sends marketing templates to users for:
- Activation: Users who signed up but haven't created invoices
- Win-back: Users who haven't been active recently
- Low Balance: Users running low on invoice credits

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

logger = logging.getLogger(__name__)


class CampaignType(str, Enum):
    """Available marketing campaign types."""
    ACTIVATION_WELCOME = "activation_welcome"
    WIN_BACK_REMINDER = "win_back_reminder"
    LOW_BALANCE_REMINDER = "low_balance_reminder"


# Template configurations
CAMPAIGN_TEMPLATES = {
    CampaignType.ACTIVATION_WELCOME: {
        "template_name": "activation_welcome",
        "language": "en",
        "description": "Users who signed up but haven't created invoices",
        "params": ["name"],  # {{1}} = user name
    },
    CampaignType.WIN_BACK_REMINDER: {
        "template_name": "win_back_reminder",
        "language": "en",
        "description": "Users inactive for 14+ days",
        "params": ["name"],  # {{1}} = user name
    },
    CampaignType.LOW_BALANCE_REMINDER: {
        "template_name": "low_balance_reminder",
        "language": "en",
        "description": "Users with low invoice balance",
        "params": ["name", "remaining_invoices"],  # {{1}} = name, {{2}} = remaining count
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
        """
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
        
        return list(self.db.execute(stmt).scalars().all())

    def get_winback_candidates(self, inactive_days: int = 14, limit: int = 100) -> list[User]:
        """Get users who haven't created invoices recently.
        
        Args:
            inactive_days: Consider users inactive if no invoice in this many days
            limit: Maximum users to return
        """
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
        
        return list(self.db.execute(stmt).scalars().all())

    def get_low_balance_candidates(self, threshold: int = 5, limit: int = 100) -> list[tuple[User, int]]:
        """Get users with low invoice balance.
        
        Args:
            threshold: Users with this many or fewer invoices remaining
            limit: Maximum users to return
            
        Returns:
            List of (User, remaining_count) tuples
        """
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
        return [(user, user.invoice_balance) for user in users]

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
            limit: Maximum messages to send
            
        Returns:
            Summary of campaign results
        """
        config = CAMPAIGN_TEMPLATES[campaign_type]
        template_name = config["template_name"]
        language = config["language"]
        
        results = {
            "campaign": campaign_type.value,
            "template": template_name,
            "dry_run": dry_run,
            "candidates": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }
        
        # Get candidates based on campaign type
        if campaign_type == CampaignType.ACTIVATION_WELCOME:
            candidates = [(u, None) for u in self.get_activation_candidates(limit=limit)]
        elif campaign_type == CampaignType.WIN_BACK_REMINDER:
            candidates = [(u, None) for u in self.get_winback_candidates(limit=limit)]
        elif campaign_type == CampaignType.LOW_BALANCE_REMINDER:
            candidates = self.get_low_balance_candidates(limit=limit)
        else:
            logger.error("Unknown campaign type: %s", campaign_type)
            return results
        
        results["candidates"] = len(candidates)
        
        for user, extra_data in candidates:
            if not user.phone:
                results["skipped"] += 1
                continue
            
            user_name = user.name or "there"
            phone = user.phone
            
            # Build template components
            if campaign_type == CampaignType.LOW_BALANCE_REMINDER:
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
                # activation_welcome and win_back_reminder only have 1 param
                components = [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": user_name},
                        ],
                    }
                ]
            
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
                    })
                    logger.warning("[CAMPAIGN] Failed to send %s to %s", template_name, user_name)
        
        logger.info(
            "[CAMPAIGN] %s complete: %d sent, %d failed, %d skipped",
            campaign_type.value, results["sent"], results["failed"], results["skipped"]
        )
        
        return results

    def send_to_single_user(
        self,
        phone: str,
        campaign_type: CampaignType,
        user_name: str = "there",
        extra_params: dict[str, str] | None = None,
    ) -> bool:
        """Send a marketing template to a single user.
        
        Args:
            phone: User's phone number
            campaign_type: Type of campaign/template to send
            user_name: User's name for personalization
            extra_params: Additional parameters for the template
            
        Returns:
            True if sent successfully
        """
        config = CAMPAIGN_TEMPLATES[campaign_type]
        template_name = config["template_name"]
        language = config["language"]
        
        if campaign_type == CampaignType.LOW_BALANCE_REMINDER:
            remaining = extra_params.get("remaining_invoices", "5") if extra_params else "5"
            components = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": user_name},
                        {"type": "text", "text": remaining},
                    ],
                }
            ]
        else:
            components = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": user_name},
                    ],
                }
            ]
        
        return self.client.send_template(
            to=phone,
            template_name=template_name,
            language=language,
            components=components,
        )
