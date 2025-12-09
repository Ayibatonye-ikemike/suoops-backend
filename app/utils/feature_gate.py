"""
Feature gating utilities for subscription-based access control.

Tier structure:
- Free: 5 invoices/month, manual only
- Starter (₦4,500): 100 invoices/month + tax reports
- Pro (₦8,000): 200 invoices/month + custom branding + inventory
- Business (₦16,000): 300 invoices/month + voice (15 max) + OCR (15 max)
"""
import datetime as dt
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.models import models


class FeatureGate:
    """Check if user has access to premium features based on their subscription plan."""
    
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._user = None
    
    @property
    def user(self) -> models.User:
        """Lazy load user from database."""
        if self._user is None:
            self._user = self.db.query(models.User).filter(models.User.id == self.user_id).first()
            if not self._user:
                raise HTTPException(status_code=404, detail="User not found")
        return self._user
    
    def is_free_tier(self) -> bool:
        """Check if user is on free tier."""
        return self.user.plan == models.SubscriptionPlan.FREE
    
    def is_paid_tier(self) -> bool:
        """Check if user has any paid subscription."""
        return self.user.plan != models.SubscriptionPlan.FREE
    
    def get_monthly_invoice_count(self) -> int:
        """Get number of invoices created this month."""
        now = dt.datetime.now(dt.timezone.utc)
        current_month = now.month
        current_year = now.year
        
        count = (
            self.db.query(func.count(models.Invoice.id))
            .filter(
                models.Invoice.issuer_id == self.user_id,
                extract('month', models.Invoice.created_at) == current_month,
                extract('year', models.Invoice.created_at) == current_year,
            )
            .scalar()
        )
        return count or 0
    
    def can_create_invoice(self) -> tuple[bool, str | None]:
        """
        Check if user can create another invoice this month.
        
        Returns:
            (can_create: bool, error_message: str | None)
        """
        plan = self.user.plan
        limit = plan.invoice_limit
        
        current_count = self.get_monthly_invoice_count()
        
        if current_count >= limit:
            if self.is_free_tier():
                return False, (
                    f"You've reached the free tier limit of {limit} invoices per month. "
                    "Upgrade to a paid plan to create more invoices and unlock premium features."
                )
            else:
                return False, (
                    f"You've reached your {plan.value} plan limit of {limit} invoices per month. "
                    "Upgrade to a higher plan for more invoices."
                )
        
        return True, None
    
    def require_paid_plan(self, feature_name: str = "This feature") -> None:
        """
        Raise HTTPException if user is not on a paid plan.
        
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
            HTTPException: 403 if invoice limit reached
        """
        can_create, error_msg = self.can_create_invoice()
        if not can_create:
            current_count = self.get_monthly_invoice_count()
            limit = self.user.plan.invoice_limit
            
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "invoice_limit_reached",
                    "message": error_msg,
                    "current_count": current_count,
                    "limit": limit,
                    "current_plan": self.user.plan.value,
                    "upgrade_url": "/subscription/initialize"
                }
            )
    
    def get_monthly_voice_ocr_count(self) -> int:
        """
        Get number of voice + OCR invoices created this month.
        Used for Business plan 5% quota enforcement.
        """
        # TODO: Track voice/OCR invoices separately in database
        # For now, return 0 (will implement proper tracking in next iteration)
        return 0
    
    def can_use_voice_ocr(self) -> tuple[bool, str | None]:
        """
        Check if user can use voice/OCR features (Business plan with quota check).
        
        Business plan: 5% quota (15 invoices out of 300)
        Enterprise: Unlimited
        
        Returns:
            (can_use: bool, error_message: str | None)
        """
        plan = self.user.plan
        features = plan.features
        
        # Check if plan has voice/OCR access at all
        if not features.get("voice_invoice") or not features.get("photo_invoice_ocr"):
            return False, (
                "Voice invoices and Photo OCR are only available on the Business plan. "
                "Upgrade to unlock these premium features."
            )
        
        # Business plan: check quota (15 out of 300)
        if plan == models.SubscriptionPlan.BUSINESS:
            quota = features.get("voice_ocr_quota", 15)  # 15 premium invoices
            current_count = self.get_monthly_voice_ocr_count()
            
            if current_count >= quota:
                return False, (
                    f"You've reached your Business plan voice/OCR quota of {quota} premium invoices per month. "
                    f"You can still create {plan.invoice_limit - self.get_monthly_invoice_count()} "
                    "manual invoices this month."
                )
            
            return True, None
        
        # Shouldn't reach here, but safe fallback
        return False, "Voice/OCR not available on your plan"
    
    def check_voice_ocr_quota(self) -> None:
        """
        Check voice/OCR quota and raise exception if exceeded.
        
        Raises:
            HTTPException: 403 if quota exceeded or feature not available
        """
        can_use, error_msg = self.can_use_voice_ocr()
        if not can_use:
            quota = int(self.user.plan.invoice_limit * 0.05) if self.user.plan == models.SubscriptionPlan.BUSINESS else 0
            current_count = self.get_monthly_voice_ocr_count()
            
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "voice_ocr_quota_exceeded" if current_count >= quota else "voice_ocr_not_available",
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
    Convenience function to check voice/OCR quota for Business plan.
    
    Args:
        db: Database session
        user_id: User ID to check
    
    Raises:
        HTTPException: 403 if quota exceeded or feature not available
    """
    gate = FeatureGate(db, user_id)
    gate.check_voice_ocr_quota()


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
