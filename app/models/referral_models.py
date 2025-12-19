"""
Referral system models for tracking referral codes, referrals, and rewards.

BILLING MODEL:
- Free signup referrals: 8 signups → 100 free invoices (₦2,500 value)
- Paid subscription referrals: 2 Pro/Business signups → 100 free invoices (₦2,500 value)

Note: Starter plan has no monthly subscription (pay-per-invoice only).
Only Pro (₦5,000/month) and Business (₦10,000/month) count as paid referrals.

Budget: ₦500,000 = ~200 rewards from free referrals = 1,600 potential new users
"""
from __future__ import annotations

import datetime as dt
import enum
import secrets
import string
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def generate_referral_code() -> str:
    """Generate a unique 8-character referral code (uppercase alphanumeric)."""
    alphabet = string.ascii_uppercase + string.digits
    # Remove ambiguous characters (0, O, I, 1, L)
    alphabet = alphabet.replace('0', '').replace('O', '').replace('I', '').replace('1', '').replace('L', '')
    return ''.join(secrets.choice(alphabet) for _ in range(8))


class ReferralType(str, enum.Enum):
    """Type of referral based on referred user's action."""
    FREE_SIGNUP = "free_signup"  # Referred user signed up (free/starter tier)
    PAID_SIGNUP = "paid_signup"  # Referred user subscribed to Pro or Business plan


class ReferralStatus(str, enum.Enum):
    """Status of a referral."""
    PENDING = "pending"  # User signed up but not yet verified/confirmed
    COMPLETED = "completed"  # Referral is valid and counted
    EXPIRED = "expired"  # Referral expired (user never completed action)
    FRAUDULENT = "fraudulent"  # Detected as abuse


class RewardStatus(str, enum.Enum):
    """Status of a referral reward."""
    PENDING = "pending"  # Reward earned but not yet applied
    APPLIED = "applied"  # Reward has been applied to user's account
    EXPIRED = "expired"  # Reward expired before being used


if TYPE_CHECKING:
    from app.models.models import User


class ReferralCode(Base):
    """
    Unique referral code for each user.
    Each user gets one code that they can share.
    """
    __tablename__ = "referral_code"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="referral_code")
    referrals: Mapped[list["Referral"]] = relationship(
        "Referral",
        back_populates="referral_code",
        foreign_keys="Referral.referral_code_id",
    )


class Referral(Base):
    """
    Track each referral: who referred whom.
    """
    __tablename__ = "referral"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    referral_code_id: Mapped[int] = mapped_column(ForeignKey("referral_code.id"), index=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)  # The user who shared the code
    referred_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True, index=True)  # The new user
    
    # Type and status
    referral_type: Mapped[ReferralType] = mapped_column(
        Enum(ReferralType),
        default=ReferralType.FREE_SIGNUP,
    )
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus),
        default=ReferralStatus.PENDING,
    )
    
    # Timestamps
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Anti-abuse tracking
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    referral_code: Mapped[ReferralCode] = relationship(
        "ReferralCode",
        back_populates="referrals",
        foreign_keys=[referral_code_id],
    )
    referrer: Mapped["User"] = relationship("User", foreign_keys=[referrer_id])
    referred: Mapped["User"] = relationship("User", foreign_keys=[referred_id])


class ReferralReward(Base):
    """
    Track rewards earned and applied from referrals.
    """
    __tablename__ = "referral_reward"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)  # The referrer who earned the reward
    
    # Reward details
    reward_type: Mapped[str] = mapped_column(String(50))  # e.g., "free_month_starter"
    reward_description: Mapped[str] = mapped_column(String(255))  # e.g., "1 month free Starter plan"
    
    # Thresholds at time of earning (for audit)
    free_referrals_count: Mapped[int] = mapped_column(Integer, default=0)  # How many free signups at time of reward
    paid_referrals_count: Mapped[int] = mapped_column(Integer, default=0)  # How many paid signups at time of reward
    
    # Status
    status: Mapped[RewardStatus] = mapped_column(
        Enum(RewardStatus),
        default=RewardStatus.PENDING,
    )
    
    # Timestamps
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    applied_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="referral_rewards")


# Referral thresholds (configurable)
# NEW BILLING MODEL: Rewards give invoice packs instead of subscription time
REFERRAL_THRESHOLDS = {
    "free_signup": {
        "required": 8,  # 8 free signups = 1 reward
        "reward_type": "invoice_pack",
        "reward_description": "100 free invoices (₦2,500 value)",
        "invoices_reward": 100,
    },
    "paid_signup": {
        "required": 2,  # 2 paid signups = 1 reward
        "reward_type": "invoice_pack",
        "reward_description": "100 free invoices (₦2,500 value)",
        "invoices_reward": 100,
    },
}
