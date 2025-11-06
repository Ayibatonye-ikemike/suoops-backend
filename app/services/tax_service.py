"""
Tax Profile Management Service.

Handles:
- Business classification (small/medium/large)
- Tax profile updates
- Automatic tax rate determination

Single Responsibility: Tax profile management
"""
import logging
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy.orm import Session

from app.models.models import User
from app.models.tax_models import TaxProfile, BusinessSize

logger = logging.getLogger(__name__)


class BusinessClassifier:
    """
    Business size classification (SRP: Classification logic only).
    
    NRS 2026 thresholds:
    - Small: Turnover ≤ ₦100M AND Assets ≤ ₦250M
    - Medium: Above small but < ₦500M turnover
    - Large: ₦500M+ turnover
    """
    
    SMALL_TURNOVER_THRESHOLD = Decimal("100000000")   # ₦100M
    SMALL_ASSETS_THRESHOLD = Decimal("250000000")     # ₦250M
    MEDIUM_TURNOVER_THRESHOLD = Decimal("500000000")  # ₦500M
    
    @classmethod
    def classify(cls, turnover: Decimal, assets: Decimal) -> str:
        """
        Classify business size based on NRS 2026 criteria.
        
        Args:
            turnover: Annual turnover in Naira
            assets: Total fixed assets in Naira
            
        Returns:
            BusinessSize enum value (small/medium/large)
        """
        if turnover <= cls.SMALL_TURNOVER_THRESHOLD and assets <= cls.SMALL_ASSETS_THRESHOLD:
            return BusinessSize.SMALL
        elif turnover < cls.MEDIUM_TURNOVER_THRESHOLD:
            return BusinessSize.MEDIUM
        else:
            return BusinessSize.LARGE


class TaxProfileService:
    """
    Main tax profile service (orchestrates profile operations).
    
    Manages:
    - Profile creation and retrieval
    - Profile updates
    - Business classification
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.classifier = BusinessClassifier()
    
    def get_or_create_profile(self, user_id: int) -> TaxProfile:
        """
        Get existing tax profile or create default one.
        
        Args:
            user_id: User ID
            
        Returns:
            TaxProfile instance
        """
        profile = self.db.query(TaxProfile).filter(
            TaxProfile.user_id == user_id
        ).first()
        
        if not profile:
            profile = TaxProfile(user_id=user_id)
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
            logger.info(f"Created default tax profile for user {user_id}")
        
        return profile
    
    def update_profile(
        self,
        user_id: int,
        annual_turnover: Optional[Decimal] = None,
        fixed_assets: Optional[Decimal] = None,
        tin: Optional[str] = None,
        vat_registration_number: Optional[str] = None,
        vat_registered: Optional[bool] = None
    ) -> TaxProfile:
        """
        Update tax profile with new data.
        
        Args:
            user_id: User ID
            annual_turnover: Annual business turnover
            fixed_assets: Total fixed assets value
            tin: Tax Identification Number
            vat_registration_number: VAT registration number
            vat_registered: VAT registration status
            
        Returns:
            Updated TaxProfile
        """
        profile = self.get_or_create_profile(user_id)
        
        # Update fields if provided
        if annual_turnover is not None:
            profile.annual_turnover = annual_turnover
        
        if fixed_assets is not None:
            profile.fixed_assets = fixed_assets
        
        if tin is not None:
            profile.tin = tin
        
        if vat_registration_number is not None:
            profile.vat_registration_number = vat_registration_number
        
        if vat_registered is not None:
            profile.vat_registered = vat_registered
        
        # Auto-classify business size
        if annual_turnover is not None or fixed_assets is not None:
            profile.business_size = self.classifier.classify(
                profile.annual_turnover,
                profile.fixed_assets
            )
            logger.info(
                f"User {user_id} classified as {profile.business_size} business "
                f"(turnover: ₦{profile.annual_turnover}, assets: ₦{profile.fixed_assets})"
            )
        
        self.db.commit()
        self.db.refresh(profile)
        
        return profile
    
    def get_tax_summary(self, user_id: int) -> Dict:
        """
        Get comprehensive tax profile summary.
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with classification, rates, registration status
        """
        profile = self.get_or_create_profile(user_id)
        
        return {
            "user_id": user_id,
            "business_size": profile.business_size,
            "is_small_business": profile.is_small_business,
            "classification": {
                "annual_turnover": float(profile.annual_turnover),
                "fixed_assets": float(profile.fixed_assets),
                "small_business_threshold": {
                    "turnover": 100_000_000,
                    "assets": 250_000_000
                },
                "meets_small_criteria": profile.is_small_business
            },
            "tax_rates": profile.tax_rates,
            "registration": {
                "tin": profile.tin,
                "vat_registered": profile.vat_registered,
                "vat_number": profile.vat_registration_number,
                "nrs_registered": profile.nrs_registered,
                "nrs_merchant_id": profile.nrs_merchant_id
            },
            "tax_benefits": self._get_tax_benefits(profile)
        }
    
    def _get_tax_benefits(self, profile: TaxProfile) -> Dict:
        """Get list of applicable tax benefits based on classification"""
        if profile.is_small_business:
            return {
                "company_income_tax": "EXEMPT (₦0)",
                "capital_gains_tax": "EXEMPT (₦0)",
                "development_levy": "EXEMPT (₦0)",
                "vat": "APPLICABLE (7.5%)",
                "annual_savings": "Estimated ₦2M-10M (depending on profits)"
            }
        else:
            return {
                "company_income_tax": "25% on profits",
                "capital_gains_tax": "30% on capital gains",
                "development_levy": "4% on assessable profits",
                "vat": "7.5% standard rate",
                "note": "Consider optimizing business structure for tax efficiency"
            }
