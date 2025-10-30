"""
Feature gating utilities for subscription-based access control.

Free tier: 5 invoices per month only
Paid tiers: All features unlocked + invoice limits
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
        
        # Unlimited for enterprise
        if limit is None:
            return True, None
        
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
