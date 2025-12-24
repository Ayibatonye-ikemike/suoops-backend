"""
Feature gating utilities for subscription-based access control.

NEW BILLING MODEL:
- Invoice Packs: 100 invoices for ₦2,500 (one-time purchase, never expires)
- FREE: 5 free invoices to start, then purchase packs
- STARTER: No monthly fee, just buy invoice packs + tax features
- PRO (₦5,000/mo): Premium features (branding, inventory, team, voice, API) + buy invoice packs

Invoice balance is decremented per use. All plans can purchase more packs.
Pro users keep features even when invoices are exhausted.

Note: OCR feature has been removed to focus on core invoicing.
"""
import datetime as dt
import logging
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import models


logger = logging.getLogger(__name__)

# Invoice pack pricing
INVOICE_PACK_SIZE = 100
INVOICE_PACK_PRICE = 2500  # ₦2,500


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
        - Pro/Business → Starter (keep tax features, lose premium features)
        - Invoice balance is preserved (they paid for those invoices)
        - Starter has no expiry (just buy invoice packs)
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
            # Subscription has expired - downgrade to Starter (keeps tax features)
            old_plan = user.plan.value
            user.plan = models.SubscriptionPlan.STARTER
            user.subscription_expires_at = None
            # Keep invoice_balance - they paid for those!
            self.db.commit()
            logger.info(
                "Subscription expired for user %s: downgraded from %s to STARTER (invoice balance: %d)",
                user.id, old_plan, getattr(user, 'invoice_balance', 0)
            )
    
    def is_free_tier(self) -> bool:
        """Check if user is on free tier."""
        return self.user.plan == models.SubscriptionPlan.FREE
    
    def is_paid_tier(self) -> bool:
        """Check if user has any paid subscription (not FREE)."""
        return self.user.plan != models.SubscriptionPlan.FREE
    
    def _get_invoice_balance_safe(self) -> int:
        """Safely get invoice_balance, defaulting to 5 if column doesn't exist yet."""
        return getattr(self.user, 'invoice_balance', 5)
    
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
        """
        Deduct one invoice from user's balance after creating a revenue invoice.
        
        Should be called after successfully creating a revenue invoice.
        """
        balance = self._get_invoice_balance_safe()
        if balance > 0:
            self._set_invoice_balance_safe(balance - 1)
            self.db.commit()
            logger.info(
                "Deducted 1 invoice from user %s balance (remaining: %d)",
                self.user_id, self._get_invoice_balance_safe()
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
        plan = self.user.plan
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
            quota = 15 if self.user.plan == models.SubscriptionPlan.PRO else 0
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
    features = gate.user.plan.features
    
    if not features.get(feature_key):
        feature_display = feature_name or feature_key.replace("_", " ").title()
        raise HTTPException(
            status_code=403,
            detail={
                "error": "feature_not_available",
                "message": f"{feature_display} is not available on your {gate.user.plan.value} plan. Please upgrade.",
                "current_plan": gate.user.plan.value,
                "required_feature": feature_key,
                "upgrade_url": "/subscription/initialize"
            }
        )
