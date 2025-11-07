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
from datetime import datetime, timezone
from typing import Dict, Optional
from sqlalchemy.orm import Session

from app.models.models import User
from app.models.tax_models import TaxProfile, BusinessSize

logger = logging.getLogger(__name__)


class BusinessClassifier:
    """
    Business size classification (SRP: Classification logic only).
    
    Threshold assumptions (legacy placeholder; verify with FIRS current guidance):
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
    Classify business size based on assumed criteria.
        
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
                "firs_registered": profile.firs_registered,
                "firs_merchant_id": profile.firs_merchant_id
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

    # ---------------- Compliance & Eligibility (merged from legacy service) -----------------

    SMALL_BUSINESS_TURNOVER_LIMIT = Decimal("100000000")  # ₦100M
    SMALL_BUSINESS_ASSETS_LIMIT = Decimal("250000000")    # ₦250M

    def check_small_business_eligibility(self, user_id: int) -> Dict[str, object]:
        """Return detailed small business eligibility info (unified schema)."""
        profile = self.get_or_create_profile(user_id)
        is_eligible = profile.is_small_business
        turnover_remaining = self.SMALL_BUSINESS_TURNOVER_LIMIT - profile.annual_turnover
        assets_remaining = self.SMALL_BUSINESS_ASSETS_LIMIT - profile.fixed_assets
        benefits = []
        if is_eligible:
            benefits = [
                "0% Company Income Tax (CIT)",
                "0% Capital Gains Tax (CGT)",
                "0% Development Levy",
                "Simplified filing requirements",
                "Reduced compliance burden",
            ]
        return {
            "eligible": is_eligible,
            "business_size": profile.business_size,
            "current_turnover": float(profile.annual_turnover),
            "turnover_limit": float(self.SMALL_BUSINESS_TURNOVER_LIMIT),
            "turnover_remaining": float(turnover_remaining) if is_eligible else 0,
            "current_assets": float(profile.fixed_assets),
            "assets_limit": float(self.SMALL_BUSINESS_ASSETS_LIMIT),
            "assets_remaining": float(assets_remaining) if is_eligible else 0,
            "tax_rates": profile.tax_rates,
            "benefits": benefits,
            "approaching_limit": (
                (turnover_remaining < Decimal("10000000"))
                or (assets_remaining < Decimal("25000000"))
            ) if is_eligible else False,
        }

    def get_compliance_summary(self, user_id: int) -> Dict[str, object]:
        """Unified compliance summary (TIN/VAT/NRS)."""
        profile = self.get_or_create_profile(user_id)
        requirements = {
            "tin_registered": profile.tin is not None,
            "vat_registered": profile.vat_registered,
            "firs_registered": profile.firs_registered,
        }
        completed = sum(1 for v in requirements.values() if v)
        total = len(requirements)
        compliance_score = (completed / total) * 100 if total else 0
        if compliance_score == 100:
            status = "fully_compliant"
        elif compliance_score >= 66:
            status = "mostly_compliant"
        elif compliance_score >= 33:
            status = "partially_compliant"
        else:
            status = "non_compliant"
        next_actions: list[str] = []
        if not profile.tin:
            next_actions.append("Register for Tax Identification Number (TIN)")
        if not profile.vat_registered and profile.annual_turnover > Decimal("25000000"):
            next_actions.append("Register for VAT (turnover exceeds ₦25M)")
        if not profile.firs_registered:
            next_actions.append("Register for forthcoming FIRS fiscalization/e-invoicing")
        return {
            "compliance_status": status,
            "compliance_score": compliance_score,
            "requirements": requirements,
            "next_actions": next_actions,
            "business_size": profile.business_size,
            "small_business_benefits": profile.is_small_business,
            "last_check": profile.last_compliance_check.isoformat() if profile.last_compliance_check else None,
        }

    def update_compliance_check(self, user_id: int) -> TaxProfile:
        profile = self.get_or_create_profile(user_id)
        # Use timezone-aware UTC timestamp for consistency
        profile.last_compliance_check = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    # ---------------- Development Levy Computation (minimal compliance helper) -----------------
    def compute_development_levy(self, user_id: int, assessable_profit: Decimal) -> Dict[str, object]:
        """Compute development levy on assessable profits.

        Rules (2026 draft):
        - Small businesses: Exempt (0%)
        - Others: 4% of assessable profits

        Args:
            user_id: User ID owning the profile
            assessable_profit: Profit base for levy calculation (>= 0)

        Returns:
            dict with applicability and amount
        """
        if assessable_profit < 0:
            raise ValueError("assessable_profit must be >= 0")
        profile = self.get_or_create_profile(user_id)
        applies = not profile.is_small_business
        rate = Decimal("0.04") if applies else Decimal("0")
        amount = (assessable_profit * rate).quantize(Decimal("0.01"))
        return {
            "user_id": user_id,
            "business_size": profile.business_size,
            "is_small_business": profile.is_small_business,
            "assessable_profit": float(assessable_profit),
            "levy_rate_percent": float(rate * 100),
            "levy_applicable": applies,
            "levy_amount": float(amount),
            "exemption_reason": "small_business" if not applies else None,
        }

    # ---------------- Tax constants (exposed to frontend) -----------------
    def get_tax_constants(self) -> Dict[str, object]:
        """Return static tax thresholds & rates for UI consumption."""
        return {
            "small_business_turnover_limit": float(self.SMALL_BUSINESS_TURNOVER_LIMIT),
            "small_business_assets_limit": float(self.SMALL_BUSINESS_ASSETS_LIMIT),
            "development_levy_rate": 0.04,  # 4%
            "cit_rate_standard": 25,
            "cgt_rate_company": 30,
            "vat_rate_standard": 7.5,
        }
