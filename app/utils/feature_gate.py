"""
Feature gating utilities for subscription-based access control.

NEW BILLING MODEL:
- Invoice Packs: 50 invoices for ₦1,250 (one-time purchase, never expires)
- FREE: 2 free invoices to start, then purchase packs. Tax features included.
- PRO (₦3,250/mo): Premium features (branding, inventory, team, voice) + buy invoice packs

Note: STARTER plan removed. Users start FREE, buy packs as needed.
Frontend shows "Starter" as a UX label for non-Pro users.
Invoice balance is decremented per use. All plans can purchase more packs.
Pro users keep features even when invoices are exhausted.
"""
import datetime as dt
import logging

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import models

logger = logging.getLogger(__name__)

# Invoice pack pricing
INVOICE_PACK_SIZE = 50
INVOICE_PACK_PRICE = 1250  # ₦1,250

# Small pack option
INVOICE_SMALL_PACK_SIZE = 25
INVOICE_SMALL_PACK_PRICE = 625  # ₦625

PACK_OPTIONS = {
    "standard": {"size": INVOICE_PACK_SIZE, "price": INVOICE_PACK_PRICE},
    "small": {"size": INVOICE_SMALL_PACK_SIZE, "price": INVOICE_SMALL_PACK_PRICE},
}


class FeatureGate:
    """Check if user has access to features and invoice balance."""
    
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._user = None
    
    @property
    def user(self) -> models.User:
        """Lazy load user from database and check subscription expiry."""
        if self._user is None:
            self._user = self.db.query(models.User).filter(models.User.id == self.user_id).first()
            if not self._user:
                raise HTTPException(status_code=404, detail="User not found")
            # Check if paid subscription (Pro/Business) has expired
            self._check_subscription_expiry()
        return self._user
    
    def _check_subscription_expiry(self) -> None:
        """
        Check if user's Pro/Business subscription has expired.
        
        When expired:
        - Pro/Business → FREE (lose all premium features)
        - Invoice balance is preserved (they paid for those invoices)
        - FREE users can still buy invoice packs as needed
        """
        user = self._user
        now = dt.datetime.now(dt.timezone.utc)
        
        # Only Pro and Business have monthly subscriptions that can expire
        if not user.plan.has_monthly_subscription:
            return
        
        if user.subscription_expires_at is None:
            return  # No expiry set (legacy data)
        
        expiry = user.subscription_expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=dt.timezone.utc)
        
        if now > expiry:
            # Subscription has expired - downgrade to FREE (basic invoicing only)
            old_plan = user.plan.value
            user.plan = models.SubscriptionPlan.FREE
            user.subscription_expires_at = None
            # Keep invoice_balance - they paid for those!
            self.db.commit()
            logger.info(
                "Subscription expired for user %s: downgraded from %s to FREE (invoice balance: %d)",
                user.id, old_plan, getattr(user, 'invoice_balance', 0)
            )
    
    def is_free_tier(self) -> bool:
        """Check if user is on free tier (respects pro_override)."""
        return self.user.effective_plan == models.SubscriptionPlan.FREE
    
    def is_paid_tier(self) -> bool:
        """Check if user has any paid subscription (not FREE, respects pro_override)."""
        return self.user.effective_plan != models.SubscriptionPlan.FREE
    
    def _get_invoice_balance_safe(self) -> int:
        """Safely get invoice_balance, defaulting to 2 if column doesn't exist yet."""
        return getattr(self.user, 'invoice_balance', 2)
    
    def _set_invoice_balance_safe(self, value: int) -> None:
        """Safely set invoice_balance if column exists."""
        if hasattr(self.user, 'invoice_balance'):
            self.user.invoice_balance = value
    
    def get_invoice_balance(self) -> int:
        """Get user's current invoice balance."""
        return self._get_invoice_balance_safe()
    
    def can_create_invoice(self) -> tuple[bool, str | None]:
        """
        Check if user has invoice balance to create an invoice.
        
        NEW MODEL: Check invoice_balance instead of monthly limits.
        All plans work the same - need balance >= 1 to create invoice.
        
        Returns:
            (can_create: bool, error_message: str | None)
        """
        balance = self._get_invoice_balance_safe()
        
        if balance <= 0:
            return False, (
                "You've used all your invoices! "
                f"Purchase an invoice pack (₦{INVOICE_PACK_PRICE:,} for {INVOICE_PACK_SIZE} invoices) to continue."
            )
        
        return True, None
    
    def deduct_invoice(self) -> None:
        """Atomically deduct one invoice from user's balance.

        Uses SELECT FOR UPDATE to prevent race conditions where concurrent
        requests could both pass the balance check before either deducts.
        """
        from sqlalchemy import text

        # Lock the user row and read the current balance atomically
        result = self.db.execute(
            text("SELECT invoice_balance FROM \"user\" WHERE id = :uid FOR UPDATE"),
            {"uid": self.user_id},
        ).fetchone()

        if not result:
            return

        balance = result[0] or 0
        if balance <= 0:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "invoice_balance_exhausted",
                    "message": "No invoice balance remaining.",
                    "invoice_balance": 0,
                },
            )

        self.db.execute(
            text("UPDATE \"user\" SET invoice_balance = invoice_balance - 1 WHERE id = :uid AND invoice_balance > 0"),
            {"uid": self.user_id},
        )
        self.db.commit()
        # Refresh the ORM object so subsequent reads see the new balance
        self.db.refresh(self.user)
        logger.info(
            "Deducted 1 invoice from user %s balance (remaining: %d)",
            self.user_id, self._get_invoice_balance_safe(),
        )
    
    def add_invoice_pack(self, quantity: int = 1) -> int:
        """
        Add invoice pack(s) to user's balance.
        
        Args:
            quantity: Number of packs to add (default 1)
            
        Returns:
            New invoice balance
        """
        invoices_to_add = INVOICE_PACK_SIZE * quantity
        current_balance = self._get_invoice_balance_safe()
        self._set_invoice_balance_safe(current_balance + invoices_to_add)
        self.db.commit()
        new_balance = self._get_invoice_balance_safe()
        logger.info(
            "Added %d invoices (%d packs) to user %s balance (new balance: %d)",
            invoices_to_add, quantity, self.user_id, new_balance
        )
        return new_balance

    def get_monthly_invoice_count(self) -> int:
        """Return count of revenue invoices created in the current month.

        This is primarily used for dashboards/analytics and legacy UI.
        It does not affect invoice balance enforcement (which is balance-based).
        """
        now = dt.datetime.now(dt.timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = (
            self.db.query(func.count(models.Invoice.id))
            .filter(
                models.Invoice.issuer_id == self.user_id,
                models.Invoice.invoice_type == "revenue",
                models.Invoice.created_at >= month_start,
            )
            .scalar()
        )
        return int(count or 0)
    
    def require_paid_plan(self, feature_name: str = "This feature") -> None:
        """
        Raise HTTPException if user is not on a paid plan (FREE tier).
        
        Note: Starter, Pro, and Business are all considered "paid" for feature access.
        
        Args:
            feature_name: Name of the feature being accessed (for error message)
        
        Raises:
            HTTPException: 403 if user is on free tier
        """
        if self.is_free_tier():
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "premium_feature_required",
                    "message": f"{feature_name} is only available on paid plans. Upgrade to unlock this feature.",
                    "current_plan": self.user.plan.value,
                    "upgrade_url": "/subscription/initialize"
                }
            )
    
    def check_invoice_creation(self) -> None:
        """
        Check if user can create invoice and raise exception if not.
        
        Raises:
            HTTPException: 403 if no invoice balance
        """
        can_create, error_msg = self.can_create_invoice()
        if not can_create:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "invoice_balance_exhausted",
                    "message": error_msg,
                    "invoice_balance": self._get_invoice_balance_safe(),
                    "pack_price": INVOICE_PACK_PRICE,
                    "pack_size": INVOICE_PACK_SIZE,
                    "current_plan": self.user.plan.value,
                    "purchase_url": "/invoices/purchase-pack"
                }
            )
    
    def get_monthly_voice_count(self) -> int:
        """
        Get number of voice invoices created this month.
        Used for Pro plan quota enforcement.
        """
        # TODO: Track voice invoices separately in database
        # For now, return 0 (will implement proper tracking in next iteration)
        return 0
    
    def can_use_voice(self) -> tuple[bool, str | None]:
        """
        Check if user can use voice features (Pro plan with quota check).
        
        Pro plan: 15 voice invoices per month
        
        Returns:
            (can_use: bool, error_message: str | None)
        """
        plan = self.user.effective_plan
        features = plan.features
        
        # Check if plan has voice access at all
        if not features.get("voice_invoice"):
            return False, (
                "Voice invoices are only available on the Pro plan. "
                "Upgrade to unlock this premium feature."
            )
        
        # Pro plan: check quota (15 per month)
        if plan == models.SubscriptionPlan.PRO:
            quota = features.get("voice_quota", 15)  # 15 premium invoices
            current_count = self.get_monthly_voice_count()
            
            if current_count >= quota:
                return False, (
                    f"You've reached your Pro plan voice quota of {quota} premium invoices per month. "
                    "You can still create manual text invoices."
                )
            
            return True, None
        
        # Shouldn't reach here, but safe fallback
        return False, "Voice not available on your plan"
    
    def check_voice_quota(self) -> None:
        """
        Check voice quota and raise exception if exceeded.
        
        Raises:
            HTTPException: 403 if quota exceeded or feature not available
        """
        can_use, error_msg = self.can_use_voice()
        if not can_use:
            quota = 15 if self.user.effective_plan == models.SubscriptionPlan.PRO else 0
            current_count = self.get_monthly_voice_count()
            
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "voice_quota_exceeded" if current_count >= quota else "voice_not_available",
                    "message": error_msg,
                    "current_count": current_count,
                    "quota": quota,
                    "current_plan": self.user.plan.value,
                    "upgrade_url": "/subscription/initialize"
                }
            )


def require_paid_plan(db: Session, user_id: int, feature_name: str = "This feature") -> None:
    """
    Convenience function to check if user has paid plan.
    
    Args:
        db: Database session
        user_id: User ID to check
        feature_name: Name of feature for error message
    
    Raises:
        HTTPException: 403 if user is on free tier
    """
    gate = FeatureGate(db, user_id)
    gate.require_paid_plan(feature_name)


def check_invoice_limit(db: Session, user_id: int) -> None:
    """
    Convenience function to check invoice creation limits.
    
    Args:
        db: Database session
        user_id: User ID to check
    
    Raises:
        HTTPException: 403 if invoice limit reached
    """
    gate = FeatureGate(db, user_id)
    gate.check_invoice_creation()


def check_voice_ocr_quota(db: Session, user_id: int) -> None:
    """
    Convenience function to check voice quota for Pro plan.
    
    Note: OCR feature has been removed. This function now only checks voice quota.
    Kept the old name for backward compatibility with existing code.
    
    Args:
        db: Database session
        user_id: User ID to check
    
    Raises:
        HTTPException: 403 if quota exceeded or feature not available
    """
    gate = FeatureGate(db, user_id)
    gate.check_voice_quota()


def require_plan_feature(db: Session, user_id: int, feature_key: str, feature_name: str = None) -> None:
    """
    Check if user's plan has a specific feature.
    
    Args:
        db: Database session
        user_id: User ID to check
        feature_key: Key in plan.features dict (e.g., 'custom_branding', 'tax_automation')
        feature_name: Human-readable feature name for error message
    
    Raises:
        HTTPException: 403 if feature not available on user's plan
    """
    gate = FeatureGate(db, user_id)
    features = gate.user.effective_plan.features
    
    if not features.get(feature_key):
        feature_display = feature_name or feature_key.replace("_", " ").title()
        raise HTTPException(
            status_code=403,
            detail={
                "error": "feature_not_available",
                "message": f"{feature_display} is not available on your {gate.user.effective_plan.value} plan. Please upgrade.",
                "current_plan": gate.user.effective_plan.value,
                "required_feature": feature_key,
                "upgrade_url": "/subscription/initialize"
            }
        )
