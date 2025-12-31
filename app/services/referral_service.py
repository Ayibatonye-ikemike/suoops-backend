"""
Referral service for managing referral codes, tracking referrals, and distributing rewards.

Business rules:
- Each user gets a unique 8-character referral code
- Free signup referrals: 8 signups → 100 free invoices (₦2,500 value)
- Paid subscription referrals: 2 Pro signups → 100 free invoices (₦2,500 value)
- Note: Starter has no monthly subscription - only Pro counts as paid referrals
- Rewards expire after 90 days if not applied
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.models import User
from app.models.referral_models import (
    REFERRAL_THRESHOLDS,
    Referral,
    ReferralCode,
    ReferralReward,
    ReferralStatus,
    ReferralType,
    RewardStatus,
    generate_referral_code,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ReferralService:
    """Service for managing the referral program."""

    def __init__(self, db: Session):
        self.db = db

    # ==================== REFERRAL CODE MANAGEMENT ====================

    def get_or_create_referral_code(self, user_id: int) -> ReferralCode:
        """
        Get user's referral code or create one if it doesn't exist.
        """
        # Check for existing code
        existing = self.db.execute(
            select(ReferralCode).where(ReferralCode.user_id == user_id)
        ).scalar_one_or_none()

        if existing:
            return existing

        # Generate new unique code
        for _ in range(10):  # Max 10 attempts to avoid collision
            code = generate_referral_code()
            # Check uniqueness
            exists = self.db.execute(
                select(ReferralCode).where(ReferralCode.code == code)
            ).scalar_one_or_none()
            if not exists:
                break
        else:
            # Fallback: add user_id suffix
            code = f"{generate_referral_code()[:5]}{user_id}"

        referral_code = ReferralCode(user_id=user_id, code=code)
        self.db.add(referral_code)
        self.db.commit()
        self.db.refresh(referral_code)

        logger.info(f"Created referral code {code} for user {user_id}")
        return referral_code

    def get_code_by_string(self, code: str) -> ReferralCode | None:
        """Look up a referral code by its string value."""
        return self.db.execute(
            select(ReferralCode)
            .where(ReferralCode.code == code.upper())
            .where(ReferralCode.is_active.is_(True))
        ).scalar_one_or_none()

    def validate_referral_code(self, code: str, referred_user_id: int) -> tuple[bool, str]:
        """
        Validate a referral code for a new user.
        Returns (is_valid, error_message).
        """
        referral_code = self.get_code_by_string(code)

        if not referral_code:
            return False, "Invalid referral code"

        if referral_code.user_id == referred_user_id:
            return False, "You cannot use your own referral code"

        # Check if user was already referred
        existing_referral = self.db.execute(
            select(Referral).where(Referral.referred_id == referred_user_id)
        ).scalar_one_or_none()

        if existing_referral:
            return False, "You have already been referred by someone"

        return True, ""

    # ==================== REFERRAL TRACKING ====================

    def record_referral(
        self,
        code: str,
        referred_user_id: int,
        referral_type: ReferralType = ReferralType.FREE_SIGNUP,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Referral | None:
        """
        Record a new referral when a user signs up with a referral code.
        """
        referral_code = self.get_code_by_string(code)
        if not referral_code:
            logger.warning(f"Invalid referral code: {code}")
            return None

        # Validate
        is_valid, error = self.validate_referral_code(code, referred_user_id)
        if not is_valid:
            logger.warning(f"Invalid referral: {error}")
            return None

        referral = Referral(
            referral_code_id=referral_code.id,
            referrer_id=referral_code.user_id,
            referred_id=referred_user_id,
            referral_type=referral_type,
            status=ReferralStatus.PENDING,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(referral)
        self.db.commit()
        self.db.refresh(referral)

        logger.info(
            f"Recorded referral: user {referral_code.user_id} referred user {referred_user_id} "
            f"(type: {referral_type.value})"
        )
        return referral

    def complete_referral(self, referred_user_id: int) -> bool:
        """
        Mark a referral as completed (e.g., after user verification).
        This is called when the referred user completes signup/verification.
        """
        referral = self.db.execute(
            select(Referral)
            .where(Referral.referred_id == referred_user_id)
            .where(Referral.status == ReferralStatus.PENDING)
        ).scalar_one_or_none()

        if not referral:
            return False

        referral.status = ReferralStatus.COMPLETED
        referral.completed_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()

        logger.info(f"Completed referral for user {referred_user_id}")

        # Check if referrer has earned a reward
        self._check_and_create_reward(referral.referrer_id)

        return True

    def upgrade_referral_to_paid(self, referred_user_id: int) -> bool:
        """
        Upgrade a referral from free to paid when referred user subscribes.
        """
        referral = self.db.execute(
            select(Referral)
            .where(Referral.referred_id == referred_user_id)
            .where(Referral.status == ReferralStatus.COMPLETED)
        ).scalar_one_or_none()

        if not referral:
            return False

        if referral.referral_type == ReferralType.PAID_SIGNUP:
            return True  # Already paid

        referral.referral_type = ReferralType.PAID_SIGNUP
        self.db.commit()

        logger.info(f"Upgraded referral for user {referred_user_id} to paid")

        # Re-check rewards (paid referrals have lower threshold)
        self._check_and_create_reward(referral.referrer_id)

        return True

    # ==================== REWARD MANAGEMENT ====================

    def _check_and_create_reward(self, referrer_id: int) -> ReferralReward | None:
        """
        Check if referrer has earned a new reward and create it.
        """
        # Get counts of completed referrals
        free_count = self._get_completed_referral_count(referrer_id, ReferralType.FREE_SIGNUP)
        paid_count = self._get_completed_referral_count(referrer_id, ReferralType.PAID_SIGNUP)

        # Get count of rewards already earned
        rewards_earned = self._get_rewards_count(referrer_id)

        # Calculate how many rewards should be earned based on thresholds
        # Paid referrals (2 = 1 reward)
        paid_rewards = paid_count // REFERRAL_THRESHOLDS["paid_signup"]["required"]
        # Free referrals (8 = 1 reward)
        free_rewards = free_count // REFERRAL_THRESHOLDS["free_signup"]["required"]

        total_rewards_deserved = paid_rewards + free_rewards

        if total_rewards_deserved > rewards_earned:
            # Create new reward
            reward = ReferralReward(
                user_id=referrer_id,
                reward_type=REFERRAL_THRESHOLDS["free_signup"]["reward_type"],
                reward_description=REFERRAL_THRESHOLDS["free_signup"]["reward_description"],
                free_referrals_count=free_count,
                paid_referrals_count=paid_count,
                status=RewardStatus.PENDING,
                expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=90),
            )
            self.db.add(reward)
            self.db.commit()
            self.db.refresh(reward)

            logger.info(
                f"Created reward for user {referrer_id}: {reward.reward_description} "
                f"(free: {free_count}, paid: {paid_count})"
            )
            return reward

        return None

    def _get_completed_referral_count(self, referrer_id: int, referral_type: ReferralType) -> int:
        """Get count of completed referrals of a specific type."""
        result = self.db.execute(
            select(func.count(Referral.id))
            .where(Referral.referrer_id == referrer_id)
            .where(Referral.referral_type == referral_type)
            .where(Referral.status == ReferralStatus.COMPLETED)
        ).scalar()
        return result or 0

    def _get_rewards_count(self, user_id: int) -> int:
        """Get count of rewards earned by user."""
        result = self.db.execute(
            select(func.count(ReferralReward.id))
            .where(ReferralReward.user_id == user_id)
        ).scalar()
        return result or 0

    def get_pending_rewards(self, user_id: int) -> list[ReferralReward]:
        """Get all pending (unclaimed) rewards for a user."""
        return list(
            self.db.execute(
                select(ReferralReward)
                .where(ReferralReward.user_id == user_id)
                .where(ReferralReward.status == RewardStatus.PENDING)
                .where(
                        (ReferralReward.expires_at.is_(None)) |
                    (ReferralReward.expires_at > dt.datetime.now(dt.timezone.utc))
                )
            ).scalars().all()
        )

    def apply_reward(self, user_id: int, reward_id: int) -> tuple[bool, str]:
        """
        Apply a pending reward to user's account.
        NEW BILLING MODEL: Rewards add invoices to balance instead of subscription time.
        Returns (success, message).
        """
        reward = self.db.execute(
            select(ReferralReward)
            .where(ReferralReward.id == reward_id)
            .where(ReferralReward.user_id == user_id)
            .where(ReferralReward.status == RewardStatus.PENDING)
        ).scalar_one_or_none()

        if not reward:
            return False, "Reward not found or already claimed"

        # Check expiry
        if reward.expires_at and reward.expires_at < dt.datetime.now(dt.timezone.utc):
            reward.status = RewardStatus.EXPIRED
            self.db.commit()
            return False, "Reward has expired"

        # Get user
        user = self.db.execute(
            select(User).where(User.id == user_id)
        ).scalar_one()

        now = dt.datetime.now(dt.timezone.utc)

        # NEW BILLING MODEL: Add invoices to balance instead of subscription time
        invoices_to_add = REFERRAL_THRESHOLDS["free_signup"].get("invoices_reward", 100)
        old_balance = getattr(user, 'invoice_balance', 5)
        
        if hasattr(user, 'invoice_balance'):
            user.invoice_balance += invoices_to_add
            new_balance = user.invoice_balance
        else:
            new_balance = old_balance + invoices_to_add

        # Mark reward as applied
        reward.status = RewardStatus.APPLIED
        reward.applied_at = now

        self.db.commit()

        logger.info(
            f"Applied referral reward {reward_id} for user {user_id}: "
            f"+{invoices_to_add} invoices (balance: {old_balance} → {new_balance})"
        )

        return True, f"Reward applied! You received {invoices_to_add} free invoices. Your new balance is {new_balance} invoices."

    # ==================== STATISTICS ====================

    def get_referral_stats(self, user_id: int) -> dict:
        """
        Get referral statistics for a user.
        """
        referral_code = self.get_or_create_referral_code(user_id)

        # Get referral counts
        free_completed = self._get_completed_referral_count(user_id, ReferralType.FREE_SIGNUP)
        paid_completed = self._get_completed_referral_count(user_id, ReferralType.PAID_SIGNUP)

        # Get pending referrals count
        pending_count = self.db.execute(
            select(func.count(Referral.id))
            .where(Referral.referrer_id == user_id)
            .where(Referral.status == ReferralStatus.PENDING)
        ).scalar() or 0

        # Get rewards
        pending_rewards = self.get_pending_rewards(user_id)
        total_rewards = self._get_rewards_count(user_id)

        # Calculate progress to next reward
        free_threshold = REFERRAL_THRESHOLDS["free_signup"]["required"]
        paid_threshold = REFERRAL_THRESHOLDS["paid_signup"]["required"]

        free_progress = free_completed % free_threshold
        paid_progress = paid_completed % paid_threshold

        return {
            "referral_code": referral_code.code,
            "referral_link": f"https://suoops.ng/register?ref={referral_code.code}",
            "total_referrals": free_completed + paid_completed,
            "pending_referrals": pending_count,
            "free_signups": free_completed,
            "paid_signups": paid_completed,
            "rewards_earned": total_rewards,
            "pending_rewards": len(pending_rewards),
            "pending_rewards_list": [
                {
                    "id": r.id,
                    "description": r.reward_description,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                }
                for r in pending_rewards
            ],
            "progress": {
                "free_signups": {
                    "current": free_progress,
                    "required": free_threshold,
                    "remaining": free_threshold - free_progress,
                },
                "paid_signups": {
                    "current": paid_progress,
                    "required": paid_threshold,
                    "remaining": paid_threshold - paid_progress,
                },
            },
        }

    def get_recent_referrals(self, user_id: int, limit: int = 10) -> list[dict]:
        """Get recent referrals for a user."""
        referrals = self.db.execute(
            select(Referral)
            .options(joinedload(Referral.referred))
            .where(Referral.referrer_id == user_id)
            .order_by(Referral.created_at.desc())
            .limit(limit)
        ).scalars().all()

        return [
            {
                "id": r.id,
                "referred_name": r.referred.name if r.referred else "Unknown",
                "type": r.referral_type.value,
                "status": r.status.value,
                "created_at": r.created_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in referrals
        ]
