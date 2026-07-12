import datetime as dt
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.api.rate_limit import limiter
from app.api.routes_admin_auth import get_current_admin
from app.core.audit import log_audit_event
from app.core.cache import cached
from app.db.session import get_db
from app.models import models
from app.models.models import SubscriptionPlan
from app.models.payment_models import PaymentStatus, PaymentTransaction
from app.utils.feature_gate import INVOICE_PACK_SIZE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Safety ceiling for admin analytics list queries that load full result sets
# into memory. Generous enough to never truncate real data at current scale,
# but prevents pathological memory blowup if the table grows unexpectedly.
ADMIN_LIST_CAP = 5000


# ── Admin response schemas ────────────────────────────────────────────

class AdminIdentity(BaseModel):
    id: int
    name: str
    role: str


class AdminRootOut(BaseModel):
    message: str
    endpoints: dict[str, str]
    authenticated_as: AdminIdentity


class UserCountOut(BaseModel):
    total_users: int
    ts: int


class PackPurchaseItem(BaseModel):
    reference: str
    amount: float
    invoices_added: int
    date: str | None = None


class UserActivity(BaseModel):
    total_invoices: int
    revenue_invoices: int
    expense_invoices: int
    total_customers: int
    has_logo: bool
    has_bank_details: bool
    wallet_balance_naira: float = 0
    invoice_balance: int
    invoices_used: int
    pack_purchases: list[PackPurchaseItem]


@router.get("/", response_model=AdminRootOut)
def admin_root(admin_user=Depends(get_current_admin)) -> dict:
    """
    Admin API root - lists available endpoints.
    """
    return {
        "message": "Admin API",
        "endpoints": {
            "GET /admin/users/count": "Get total user count (cached)",
            "GET /admin/users/stats": "Get comprehensive user statistics",
            "GET /admin/users": (
                "List all users with filtering (query params: skip, limit, plan, "
                "verified_only, search)"
            ),
            "GET /admin/users/{user_id}": "Get detailed user information including activity"
        },
        "authenticated_as": {
            "id": admin_user.id,
            "name": admin_user.name,
            "role": admin_user.role
        }
    }


class UserListItem(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    plan: str
    phone_verified: bool
    created_at: dt.datetime
    last_login: dt.datetime | None
    invoices_this_month: int
    business_name: str | None
    role: str
    pro_override: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserStats(BaseModel):
    total_users: int
    verified_users: int
    unverified_users: int
    users_by_plan: dict[str, int]
    users_registered_today: int
    users_registered_this_week: int
    users_registered_this_month: int
    active_users_last_30_days: int


class UserDetailOut(BaseModel):
    user: UserListItem
    activity: UserActivity


@router.get("/users/count", response_model=UserCountOut)
async def user_count(db: Session = Depends(get_db), admin_user=Depends(get_current_admin)) -> dict:
    import time

    async def _produce():
        total = db.query(models.User).count()
        result = {"total_users": total, "ts": int(time.time())}
        # Audit only when freshly produced (cache miss)
        log_audit_event("admin.users.count", user_id=admin_user.id, total_users=total)
        return result  # type: ignore

    return await cached("admin:total_users", 30, _produce)


@router.get("/users/stats", response_model=UserStats)
def get_user_stats(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """
    Get comprehensive user statistics.
    """
    log_audit_event("admin.users.stats", user_id=admin_user.id)
    
    now = dt.datetime.now(dt.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - dt.timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    thirty_days_ago = now - dt.timedelta(days=30)
    
    # Single aggregated query for all user stats (replaces 7 separate queries)
    from sqlalchemy import case as sa_case
    stats_row = db.query(
        func.count(models.User.id).label("total"),
        func.count(sa_case((models.User.phone_verified.is_(True), 1))).label("verified"),
        func.count(sa_case((models.User.created_at >= today_start, 1))).label("today"),
        func.count(sa_case((models.User.created_at >= week_start, 1))).label("this_week"),
        func.count(sa_case((models.User.created_at >= month_start, 1))).label("this_month"),
        func.count(sa_case((models.User.last_login >= thirty_days_ago, 1))).label("active_30d"),
    ).one()
    
    # Plan breakdown still needs group_by
    plan_counts = db.query(
        models.User.plan,
        func.count(models.User.id)
    ).group_by(models.User.plan).all()
    
    users_by_plan = {str(plan.value): count for plan, count in plan_counts}
    
    return UserStats(
        total_users=stats_row.total,
        verified_users=stats_row.verified,
        unverified_users=stats_row.total - stats_row.verified,
        users_by_plan=users_by_plan,
        users_registered_today=stats_row.today,
        users_registered_this_week=stats_row.this_week,
        users_registered_this_month=stats_row.this_month,
        active_users_last_30_days=stats_row.active_30d,
    )


@router.get("/users", response_model=list[UserListItem])
def list_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    plan: str | None = Query(None, description="Filter by plan (free, pro)"),
    verified_only: bool = Query(False, description="Show only verified users"),
    search: str | None = Query(None, description="Search by name, email, or phone")
) -> Any:
    """
    List all users with filtering and pagination.
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Max records to return (1-100)
    - **plan**: Filter by subscription plan
    - **verified_only**: Only show phone-verified users
    - **search**: Search in name, email, or phone
    """
    log_audit_event("admin.users.list", user_id=admin_user.id, skip=skip, limit=limit)
    
    query = db.query(models.User)
    
    # Apply filters
    if plan:
        try:
            plan_enum = SubscriptionPlan(plan.lower())
            query = query.filter(models.User.plan == plan_enum)
        except ValueError:
            pass  # Invalid plan, ignore filter
    
    if verified_only:
        query = query.filter(models.User.phone_verified.is_(True))
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (models.User.name.ilike(search_pattern)) |
            (models.User.email.ilike(search_pattern)) |
            (models.User.phone.ilike(search_pattern))
        )
    
    # Order by most recent first
    query = query.order_by(desc(models.User.created_at))
    
    # Pagination
    users = query.offset(skip).limit(limit).all()
    
    return [
        UserListItem(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            plan=user.plan.value,
            phone_verified=user.phone_verified,
            created_at=user.created_at,
            last_login=user.last_login,
            invoices_this_month=user.invoices_this_month,
            business_name=user.business_name,
            role=user.role,
            pro_override=getattr(user, 'pro_override', False),
        )
        for user in users
    ]


@router.get("/users/{user_id}", response_model=UserDetailOut)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """
    Get detailed information about a specific user including their activity.
    """
    log_audit_event("admin.users.detail", user_id=admin_user.id, target_user_id=user_id)
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Count invoices in a single aggregated query (eliminates N+1)
    from sqlalchemy import case as sa_case
    invoice_counts = db.query(
        func.count(models.Invoice.id).label("total"),
        func.count(sa_case((models.Invoice.invoice_type == "revenue", 1))).label("revenue"),
        func.count(sa_case((models.Invoice.invoice_type == "expense", 1))).label("expense"),
    ).filter(models.Invoice.issuer_id == user_id).one()
    
    # Count unique customers via invoices (Customer doesn't have user_id, linked through Invoice)
    total_customers = db.query(models.Customer.id).join(
        models.Invoice, models.Invoice.customer_id == models.Customer.id
    ).filter(
        models.Invoice.issuer_id == user_id
    ).distinct().count()
    
    # Get invoice balance info
    invoice_balance = getattr(user, 'invoice_balance', 0)
    
    # Get invoice pack purchases (INVPACK references)
    invoice_pack_purchases = db.query(PaymentTransaction).filter(
        PaymentTransaction.user_id == user_id,
        PaymentTransaction.reference.like("INVPACK-%"),
        PaymentTransaction.status == PaymentStatus.SUCCESS
    ).order_by(desc(PaymentTransaction.created_at)).limit(10).all()
    
    # Calculate invoices used (total created minus current balance)
    # For new users with 2 free invoices, total would be total_invoices + remaining balance - 2
    # Simpler: invoices_used = total_invoices (each invoice created consumes 1)
    invoices_used = invoice_counts.total
    
    # Build pack purchase history
    pack_purchases = []
    for purchase in invoice_pack_purchases:
        # Read actual invoices added from transaction metadata, fallback to pack size
        metadata = purchase.payment_metadata or {}
        invoices_added = metadata.get("invoices_to_add") or (
            metadata.get("quantity", 1) * INVOICE_PACK_SIZE
        )
        pack_purchases.append({
            "reference": purchase.reference,
            "amount": purchase.amount / 100,  # Convert kobo to naira
            "invoices_added": invoices_added,
            "date": purchase.created_at.isoformat() if purchase.created_at else None
        })
    
    return {
        "user": UserListItem(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            plan=user.plan.value,
            phone_verified=user.phone_verified,
            created_at=user.created_at,
            last_login=user.last_login,
            invoices_this_month=user.invoices_this_month,
            business_name=user.business_name,
            role=user.role,
            pro_override=getattr(user, 'pro_override', False),
        ),
        "activity": {
            "total_invoices": invoice_counts.total,
            "revenue_invoices": invoice_counts.revenue,
            "expense_invoices": invoice_counts.expense,
            "total_customers": total_customers,
            "has_logo": user.logo_url is not None,
            "has_bank_details": user.account_number is not None,
            "wallet_balance_naira": int(getattr(user, "wallet_balance_kobo", 0) or 0) / 100,
            "invoice_balance": invoice_balance,
            "invoices_used": invoices_used,
            "pack_purchases": pack_purchases
        }
    }


class WalletCreditIn(BaseModel):
    amount_naira: int = Field(..., gt=0, le=500_000)
    reason: str = Field(..., min_length=3, max_length=255)


@router.post("/users/{user_id}/credit-wallet")
def credit_user_wallet(
    user_id: int,
    payload: WalletCreditIn,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Credit a business's prepaid wallet as a goodwill / support gesture.

    In the flat-3%/free model the wallet is what invoices debit their fee from,
    so this lets a business invoice without the 3% wallet debit until the credit
    is used up. It is PLATFORM value (free fees), NOT a cash payout — no real
    money leaves the platform. Super-admin only + audited + capped per credit.
    """
    _require_super_admin(admin_user)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before_kobo = int(getattr(user, "wallet_balance_kobo", 0) or 0)
    user.wallet_balance_kobo = before_kobo + int(payload.amount_naira) * 100
    db.commit()

    log_audit_event(
        "admin.users.wallet_credit",
        user_id=admin_user.id,
        target_user_id=user_id,
        amount_naira=payload.amount_naira,
        reason=payload.reason,
    )
    logger.info(
        "Admin %s credited ₦%s to user %s wallet (%s)",
        admin_user.id, payload.amount_naira, user_id, payload.reason,
    )

    return {
        "user_id": user_id,
        "credited_naira": payload.amount_naira,
        "wallet_balance_naira": user.wallet_balance_kobo / 100,
        "message": f"Credited ₦{payload.amount_naira:,} to {user.name or user.email or user_id}",
    }


# ============================================================================
# Referral Statistics
# ============================================================================

class ReferralStats(BaseModel):
    total_referral_codes: int
    total_referrals: int
    completed_referrals: int
    pending_referrals: int
    expired_referrals: int
    free_signup_referrals: int
    paid_referrals: int
    total_rewards_earned: int
    pending_rewards: int
    applied_rewards: int
    expired_rewards: int
    top_referrers: list[dict]
    referrals_today: int
    referrals_this_week: int
    referrals_this_month: int
    # Commission/Payout fields
    total_commission_earned: int  # Total commission from all paid referrals (₦488 each)
    pending_payout_amount: int  # Sum of pending rewards to be paid out
    users_with_payout_bank: int  # Number of users who have set up payout bank


@router.get("/referrals/stats", response_model=ReferralStats)
def get_referral_stats(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """Get comprehensive referral program statistics."""
    from app.models.referral_models import (
        Referral,
        ReferralCode,
        ReferralReward,
        ReferralStatus,
        ReferralType,
        RewardStatus,
        REFERRAL_COMMISSION_AMOUNT,
    )
    
    log_audit_event("admin.referrals.stats", user_id=admin_user.id)
    
    now = dt.datetime.now(dt.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - dt.timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    
    # Referral codes
    total_codes = db.query(ReferralCode).count()
    
    # Referrals by status
    total_referrals = db.query(Referral).count()
    completed = db.query(Referral).filter(Referral.status == ReferralStatus.COMPLETED).count()
    pending = db.query(Referral).filter(Referral.status == ReferralStatus.PENDING).count()
    expired = db.query(Referral).filter(Referral.status == ReferralStatus.EXPIRED).count()
    
    # Referrals by type
    free_signups = db.query(Referral).filter(Referral.referral_type == ReferralType.FREE_SIGNUP).count()
    paid = db.query(Referral).filter(Referral.referral_type == ReferralType.PAID_SIGNUP).count()
    
    # Rewards
    total_rewards = db.query(ReferralReward).count()
    pending_rewards = db.query(ReferralReward).filter(ReferralReward.status == RewardStatus.PENDING).count()
    applied_rewards = db.query(ReferralReward).filter(ReferralReward.status == RewardStatus.APPLIED).count()
    expired_rewards = db.query(ReferralReward).filter(ReferralReward.status == RewardStatus.EXPIRED).count()
    
    # Time-based referrals
    referrals_today = db.query(Referral).filter(Referral.created_at >= today_start).count()
    referrals_week = db.query(Referral).filter(Referral.created_at >= week_start).count()
    referrals_month = db.query(Referral).filter(Referral.created_at >= month_start).count()
    
    # Top referrers (with paid referral count for commission calculation)
    top_referrers_query = db.query(
        Referral.referrer_id,
        func.count(Referral.id).label("referral_count"),
        func.sum(
            case(
                (Referral.referral_type == ReferralType.PAID_SIGNUP, 1),
                else_=0
            )
        ).label("paid_count")
    ).filter(
        Referral.status == ReferralStatus.COMPLETED
    ).group_by(Referral.referrer_id).order_by(
        desc("paid_count"), desc("referral_count")
    ).limit(10).all()
    
    top_referrers = []
    for referrer_id, count, paid_count in top_referrers_query:
        user = db.query(models.User).filter(models.User.id == referrer_id).first()
        if user:
            top_referrers.append({
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "referral_count": count,
                "paid_referral_count": paid_count or 0,
                "commission_earned": (paid_count or 0) * REFERRAL_COMMISSION_AMOUNT,
                "payout_bank_name": user.payout_bank_name
            })
    
    # Commission/Payout stats
    total_commission_earned = paid * REFERRAL_COMMISSION_AMOUNT  # ₦488 per paid referral
    
    # Count users with payout bank set up
    users_with_payout_bank = db.query(models.User).filter(
        models.User.payout_bank_name.isnot(None),
        models.User.payout_account_number.isnot(None)
    ).count()
    
    # Calculate pending payout amount (pending rewards * commission)
    pending_payout_amount = pending_rewards * REFERRAL_COMMISSION_AMOUNT
    
    return ReferralStats(
        total_referral_codes=total_codes,
        total_referrals=total_referrals,
        completed_referrals=completed,
        pending_referrals=pending,
        expired_referrals=expired,
        free_signup_referrals=free_signups,
        paid_referrals=paid,
        total_rewards_earned=total_rewards,
        pending_rewards=pending_rewards,
        applied_rewards=applied_rewards,
        expired_rewards=expired_rewards,
        top_referrers=top_referrers,
        referrals_today=referrals_today,
        referrals_this_week=referrals_week,
        referrals_this_month=referrals_month,
        total_commission_earned=total_commission_earned,
        pending_payout_amount=pending_payout_amount,
        users_with_payout_bank=users_with_payout_bank
    )


# ============================================================================
# Referral Payouts Management
# ============================================================================

class PayoutUserInfo(BaseModel):
    """User with pending referral payout."""
    user_id: int
    name: str
    email: str | None
    phone: str | None
    payout_bank_name: str | None
    payout_account_number: str | None
    payout_account_name: str | None
    paid_referrals: int
    commission_amount: int  # In Naira
    has_bank_details: bool

    model_config = ConfigDict(from_attributes=True)


class PayoutListResponse(BaseModel):
    """Response for payout list endpoint."""
    total_users: int
    total_amount: int
    users_with_bank: int
    users_without_bank: int
    payouts: list[PayoutUserInfo]

    model_config = ConfigDict(from_attributes=True)


def _mask_account_number(number: str | None) -> str | None:
    """Mask a bank account number to its last 4 digits so a compromised admin
    session can't exfiltrate every user's full bank account. Enough for the
    admin to eyeball-match against the account name during a payout run."""
    if not number:
        return number
    n = number.strip()
    if len(n) <= 4:
        return n
    return "•" * (len(n) - 4) + n[-4:]


@router.get("/referrals/payouts", response_model=PayoutListResponse)
def get_referral_payouts(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    month: int | None = Query(None, description="Month (1-12), defaults to current"),
    year: int | None = Query(None, description="Year, defaults to current"),
) -> Any:
    """
    Get list of all users with pending referral commission payouts.

    Aggregates actual commission rewards earned (ReferralReward records:
    first-purchase, recurring, and perpetual commissions) so the admin view
    matches what influencers see on their earnings dashboard.

    Use month/year to filter to a specific period (for the weekly/monthly
    payout run). Returns payout bank details (falling back to the user's
    invoice bank account) so you can process payments.
    """
    import re

    from app.models.referral_models import ReferralReward, RewardStatus

    log_audit_event("admin.referrals.payouts", user_id=admin_user.id, month=month, year=year)

    def _extract_amount(description: str | None) -> int:
        if not description:
            return 0
        match = re.search(r"[₦N]?([\d,]+)", description)
        if match:
            return int(match.group(1).replace(",", ""))
        return 0

    now = dt.datetime.now(dt.timezone.utc)

    # Filter by month/year if specified
    if month and year:
        start_date = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
        if month == 12:
            end_date = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
        else:
            end_date = dt.datetime(year, month + 1, 1, tzinfo=dt.timezone.utc)
    else:
        # Default to current month
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end_date = dt.datetime(now.year + 1, 1, 1, tzinfo=dt.timezone.utc)
        else:
            end_date = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # Pull all commission rewards earned in the period
    rewards = db.query(ReferralReward).filter(
        ReferralReward.reward_type.in_([
            "commission_first_purchase",
            "commission",  # legacy first-purchase type
            "commission_recurring",
            "commission_perpetual",
            "commission_online",  # storefront/online 3%-based commission
        ]),
        ReferralReward.created_at >= start_date,
        ReferralReward.created_at < end_date,
    ).all()

    # Aggregate per referrer
    by_user: dict[int, dict[str, int]] = {}
    for r in rewards:
        bucket = by_user.setdefault(r.user_id, {"amount": 0, "count": 0})
        bucket["amount"] += _extract_amount(r.reward_description)
        bucket["count"] += 1

    payouts = []
    total_amount = 0
    users_with_bank = 0
    users_without_bank = 0

    for referrer_id, agg in by_user.items():
        if agg["amount"] <= 0:
            continue
        user = db.query(models.User).filter(models.User.id == referrer_id).first()
        if not user:
            continue

        # Prefer dedicated payout account, fall back to invoice bank details
        has_payout = bool(user.payout_bank_name and user.payout_account_number)
        bank_name = user.payout_bank_name if has_payout else user.bank_name
        account_number = user.payout_account_number if has_payout else user.account_number
        account_name = user.payout_account_name if has_payout else user.account_name
        has_bank = bool(bank_name and account_number)

        payouts.append(PayoutUserInfo(
            user_id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            payout_bank_name=bank_name,
            payout_account_number=_mask_account_number(account_number),
            payout_account_name=account_name,
            paid_referrals=agg["count"],
            commission_amount=agg["amount"],
            has_bank_details=has_bank,
        ))

        total_amount += agg["amount"]
        if has_bank:
            users_with_bank += 1
        else:
            users_without_bank += 1

    # Sort by commission amount descending
    payouts.sort(key=lambda x: x.commission_amount, reverse=True)

    return PayoutListResponse(
        total_users=len(payouts),
        total_amount=total_amount,
        users_with_bank=users_with_bank,
        users_without_bank=users_without_bank,
        payouts=payouts
    )


# ============================================================================
# Influencer / Affiliate Program
# ============================================================================


class InfluencerCreate(BaseModel):
    """Payload for creating an influencer partnership."""
    user_phone: str | None = None  # Phone of existing user to link as influencer
    user_email: str | None = None  # Email of existing user to link as influencer
    influencer_name: str
    influencer_contact: str | None = None
    custom_slug: str  # vanity URL slug — letters, numbers, hyphens only
    # Current model: influencers earn a flat share of SuoOps' 3% fee on every
    # referred transaction, for life while active. The old fixed-₦ first/recurring
    # tiers are retired (Pro-pack era) and default to 0 — perpetual_pct drives it.
    commission_first: int = 0  # retired: ₦ on first purchase
    commission_recurring: int = 0  # retired: ₦ on purchases 2–N
    commission_months: int = 0  # retired: recurring window length
    commission_perpetual_pct: int = 20  # % of SuoOps' 3% commission, every referred sale, forever
    bonus_invoices: int = 3  # extra free invoices for signups
    notes: str | None = None


class InfluencerUpdate(BaseModel):
    """Payload for updating an influencer partnership."""
    influencer_name: str | None = None
    influencer_contact: str | None = None
    custom_slug: str | None = None
    commission_first: int | None = None
    commission_recurring: int | None = None
    commission_months: int | None = None
    commission_perpetual_pct: int | None = None
    bonus_invoices: int | None = None
    notes: str | None = None
    is_active: bool | None = None


class InfluencerInfo(BaseModel):
    """Influencer partnership with performance stats."""
    id: int
    code: str
    custom_slug: str | None
    influencer_name: str | None
    influencer_contact: str | None
    commission_first: int
    commission_recurring: int
    commission_months: int
    commission_perpetual_pct: int
    bonus_invoices: int
    notes: str | None
    is_active: bool
    created_at: dt.datetime
    # Performance
    total_signups: int = 0
    activated_users: int = 0  # created at least 1 invoice
    pro_conversions: int = 0  # retired (flat-3% model has no Pro) — kept for compat
    gmv_referred: int = 0  # total paid revenue (₦) generated by referred businesses
    total_commission_earned: int = 0
    signup_link: str = ""

    model_config = ConfigDict(from_attributes=True)


class InfluencerListResponse(BaseModel):
    total: int
    influencers: list[InfluencerInfo]


@router.post("/influencers", response_model=InfluencerInfo, status_code=201)
def create_influencer(
    payload: InfluencerCreate,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> Any:
    """Create a new influencer partnership linked to an existing user account."""
    import re

    from app.models.referral_models import ReferralCode, Referral, ReferralStatus, ReferralType, generate_referral_code

    log_audit_event("admin.influencer.create", user_id=admin_user.id, slug=payload.custom_slug)

    # Must provide at least one identifier to find the user
    if not payload.user_phone and not payload.user_email:
        raise HTTPException(400, "Provide the influencer's phone number or email to link their account")

    # Look up the user by phone or email
    target_user = None
    if payload.user_phone:
        phone = payload.user_phone.strip()
        # Normalize: strip leading 0, add +234 if needed
        if phone.startswith("0"):
            phone = "+234" + phone[1:]
        elif not phone.startswith("+"):
            phone = "+" + phone
        target_user = db.query(models.User).filter(models.User.phone == phone).first()
    if not target_user and payload.user_email:
        email = payload.user_email.strip().lower()
        target_user = db.query(models.User).filter(
            func.lower(models.User.email) == email
        ).first()

    if not target_user:
        raise HTTPException(404, "No user found with that phone/email. They must sign up first.")

    # Validate slug format
    slug = payload.custom_slug.strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$", slug):
        raise HTTPException(400, "Slug must be 3-50 chars: lowercase letters, numbers, hyphens. No leading/trailing hyphens.")

    # Check slug uniqueness
    existing_slug = db.query(ReferralCode).filter(
        func.lower(ReferralCode.custom_slug) == slug
    ).first()
    if existing_slug:
        raise HTTPException(409, f"Slug '{slug}' is already taken")

    # Check if this user already has a ReferralCode — upgrade it
    existing_code = db.query(ReferralCode).filter(
        ReferralCode.user_id == target_user.id
    ).first()

    if existing_code:
        # Upgrade existing code to influencer
        existing_code.is_influencer = True
        existing_code.custom_slug = slug
        existing_code.influencer_name = payload.influencer_name
        existing_code.influencer_contact = payload.influencer_contact
        existing_code.commission_first = payload.commission_first
        existing_code.commission_recurring = payload.commission_recurring
        existing_code.commission_months = payload.commission_months
        existing_code.commission_perpetual_pct = payload.commission_perpetual_pct
        existing_code.bonus_invoices = payload.bonus_invoices
        existing_code.notes = payload.notes
        existing_code.is_active = True
        db.commit()
        db.refresh(existing_code)
        code = existing_code
    else:
        # Create new referral code for this user
        code_str = generate_referral_code()
        while db.query(ReferralCode).filter(ReferralCode.code == code_str).first():
            code_str = generate_referral_code()

        code = ReferralCode(
            user_id=target_user.id,
            code=code_str,
            is_active=True,
            is_influencer=True,
            custom_slug=slug,
            influencer_name=payload.influencer_name,
            influencer_contact=payload.influencer_contact,
            commission_first=payload.commission_first,
            commission_recurring=payload.commission_recurring,
            commission_months=payload.commission_months,
            commission_perpetual_pct=payload.commission_perpetual_pct,
            bonus_invoices=payload.bonus_invoices,
            notes=payload.notes,
        )
        db.add(code)
        db.commit()
        db.refresh(code)

    return InfluencerInfo(
        id=code.id,
        code=code.code,
        custom_slug=code.custom_slug,
        influencer_name=code.influencer_name,
        influencer_contact=code.influencer_contact,
        commission_first=code.commission_first,
        commission_recurring=code.commission_recurring,
        commission_months=code.commission_months,
        commission_perpetual_pct=code.commission_perpetual_pct,
        bonus_invoices=code.bonus_invoices,
        notes=code.notes,
        is_active=code.is_active,
        created_at=code.created_at,
        signup_link=f"https://suoops.com/join/{slug}",
    )


@router.get("/influencers", response_model=InfluencerListResponse)
def list_influencers(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> Any:
    """List all influencer partnerships with performance stats."""
    from sqlalchemy import distinct

    from app.models.referral_models import (
        Referral, ReferralCode, ReferralReward,
        ReferralStatus, ReferralType, RewardStatus,
    )

    log_audit_event("admin.influencer.list", user_id=admin_user.id)

    codes = (
        db.query(ReferralCode)
        .filter(ReferralCode.is_influencer.is_(True))
        .order_by(ReferralCode.created_at.desc())
        .all()
    )

    influencers = []
    for code in codes:
        # Total signups through this code
        total_signups = (
            db.query(func.count(Referral.id))
            .filter(Referral.referral_code_id == code.id)
            .scalar()
        ) or 0

        # Users who created at least 1 invoice (activated)
        activated = 0
        gmv_referred = 0
        if total_signups > 0:
            from app.models.models import Invoice
            referred_ids = [
                r[0] for r in
                db.query(Referral.referred_id)
                .filter(Referral.referral_code_id == code.id)
                .all()
            ]
            if referred_ids:
                activated = (
                    db.query(func.count(distinct(Invoice.issuer_id)))
                    .filter(Invoice.issuer_id.in_(referred_ids))
                    .scalar()
                ) or 0
                # Total paid revenue (GMV) generated by referred businesses — the
                # real driver of this influencer's commission.
                gmv_referred = int(
                    db.query(func.coalesce(func.sum(Invoice.amount), 0))
                    .filter(
                        Invoice.issuer_id.in_(referred_ids),
                        Invoice.invoice_type == "revenue",
                        Invoice.status == "paid",
                    )
                    .scalar()
                    or 0
                )

        # Pro conversions
        pro_conversions = (
            db.query(func.count(Referral.id))
            .filter(
                Referral.referral_code_id == code.id,
                Referral.referral_type == ReferralType.PAID_SIGNUP,
            )
            .scalar()
        ) or 0

        # Total commission earned (sum of all reward descriptions with amounts)
        total_commission = 0
        rewards = (
            db.query(ReferralReward)
            .filter(ReferralReward.user_id == code.user_id)
            .all()
        )
        # Calculate from the commission structure
        total_commission = pro_conversions * code.commission_first
        # Add recurring commissions
        recurring_rewards = (
            db.query(func.count(ReferralReward.id))
            .filter(
                ReferralReward.user_id == code.user_id,
                ReferralReward.reward_type == "commission_recurring",
            )
            .scalar()
        ) or 0
        total_commission += recurring_rewards * code.commission_recurring

        # Add perpetual commissions (variable amounts — sum from reward descriptions)
        perpetual_rewards = (
            db.query(ReferralReward)
            .filter(
                ReferralReward.user_id == code.user_id,
                ReferralReward.reward_type == "commission_perpetual",
            )
            .all()
        )
        for pr in perpetual_rewards:
            # Parse amount from description "₦{amount} commission for..."
            try:
                amt_str = pr.reward_description.split("₦")[1].split(" ")[0].replace(",", "")
                total_commission += int(amt_str)
            except (IndexError, ValueError):
                total_commission += code.commission_perpetual_pct * 2000 // 100  # fallback

        influencers.append(InfluencerInfo(
            id=code.id,
            code=code.code,
            custom_slug=code.custom_slug,
            influencer_name=code.influencer_name,
            influencer_contact=code.influencer_contact,
            commission_first=code.commission_first,
            commission_recurring=code.commission_recurring,
            commission_months=code.commission_months,
            commission_perpetual_pct=code.commission_perpetual_pct,
            bonus_invoices=code.bonus_invoices,
            notes=code.notes,
            is_active=code.is_active,
            created_at=code.created_at,
            total_signups=total_signups,
            activated_users=activated,
            pro_conversions=pro_conversions,
            gmv_referred=gmv_referred,
            total_commission_earned=total_commission,
            signup_link=f"https://suoops.com/join/{code.custom_slug}" if code.custom_slug else "",
        ))

    return InfluencerListResponse(total=len(influencers), influencers=influencers)


@router.patch("/influencers/{influencer_id}", response_model=InfluencerInfo)
def update_influencer(
    influencer_id: int,
    payload: InfluencerUpdate,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> Any:
    """Update an influencer partnership's terms."""
    import re

    from app.models.referral_models import ReferralCode

    log_audit_event("admin.influencer.update", user_id=admin_user.id, influencer_id=influencer_id)

    code = db.query(ReferralCode).filter(
        ReferralCode.id == influencer_id,
        ReferralCode.is_influencer.is_(True),
    ).first()
    if not code:
        raise HTTPException(404, "Influencer not found")

    updates = payload.model_dump(exclude_unset=True)

    if "custom_slug" in updates and updates["custom_slug"]:
        slug = updates["custom_slug"].strip().lower()
        if not re.match(r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$", slug):
            raise HTTPException(400, "Invalid slug format")
        existing = db.query(ReferralCode).filter(
            func.lower(ReferralCode.custom_slug) == slug,
            ReferralCode.id != influencer_id,
        ).first()
        if existing:
            raise HTTPException(409, f"Slug '{slug}' is already taken")
        updates["custom_slug"] = slug

    for key, value in updates.items():
        setattr(code, key, value)

    db.commit()
    db.refresh(code)

    return InfluencerInfo(
        id=code.id,
        code=code.code,
        custom_slug=code.custom_slug,
        influencer_name=code.influencer_name,
        influencer_contact=code.influencer_contact,
        commission_first=code.commission_first,
        commission_recurring=code.commission_recurring,
        commission_months=code.commission_months,
        commission_perpetual_pct=code.commission_perpetual_pct,
        bonus_invoices=code.bonus_invoices,
        notes=code.notes,
        is_active=code.is_active,
        created_at=code.created_at,
        signup_link=f"https://suoops.com/join/{code.custom_slug}" if code.custom_slug else "",
    )


# ============================================================================
# SME Concierge Onboarding
# ============================================================================

# Tailored WhatsApp messages by business type
_SME_MESSAGES: dict[str, str] = {
    "bar_restaurant": (
        "🍻 *Welcome to SuoOps, {name}!*\n\n"
        "Your bar *{business}* is all set up with Pro features. "
        "Here's everything you can do:\n\n"
        "📱 *Invoice a customer:*\n"
        "_invoice Chidi 08012345678, 5000 drinks, 3000 pepper soup_\n\n"
        "💰 *Check who owes you:*\n"
        "_owed_\n"
        "→ Reply with the number to remind or mark paid\n"
        "→ SuoOps auto-reminds customers who haven't paid\n\n"
        "📦 *Track expenses:*\n"
        "_expense: 50000 beer supply_\n\n"
        "🛒 *Product catalog & inventory:*\n"
        "Add your drinks and menu items on the dashboard at "
        "suoops.com → Products. Set stock levels and get "
        "low-stock alerts so you never run out.\n"
        "Reply _products_ here to browse your catalog.\n\n"
        "📊 *Business reports & analytics:*\n"
        "_report_ — daily summary, revenue trends, "
        "top customers, and cash position\n\n"
        "🧾 *Tax reports:*\n"
        "_tax report_ — auto-generated for FIRS compliance\n\n"
        "🎨 *Brand your invoices:*\n"
        "Upload your logo at suoops.com → Settings. "
        "Every invoice PDF will carry your branding.\n\n"
        "👥 *Your team:*\n"
        "Your staff will receive invite emails shortly. "
        "Each person invoices from their own WhatsApp — "
        "you'll see who created what on the dashboard.\n\n"
        "🖨️ *Print & share invoices:*\n"
        "Every invoice generates a professional PDF. "
        "Download it, print it, or send it directly to "
        "your customers via WhatsApp or email.\n\n"
        "🌐 *Dashboard:* suoops.com — full analytics, "
        "inventory, customer insights & more\n\n"
        "Need help? Just reply *help* anytime 🙂"
    ),
    "salon_beauty": (
        "💅 *Welcome to SuoOps, {name}!*\n\n"
        "Your salon *{business}* is all set up with Pro features. "
        "Here's everything you can do:\n\n"
        "📱 *Invoice a client:*\n"
        "_invoice Amaka 08098765432, 15000 braids, 5000 nails_\n\n"
        "💰 *Check unpaid services:*\n"
        "_owed_\n"
        "→ SuoOps auto-reminds clients who haven't paid\n\n"
        "📦 *Track product expenses:*\n"
        "_expense: 25000 hair extensions_\n\n"
        "🛒 *Product catalog & inventory:*\n"
        "Add your services and products (hair, nails, lashes) "
        "at suoops.com → Products. Set stock levels for "
        "extensions and supplies — get alerts before you run out.\n"
        "Reply _products_ to browse your catalog.\n\n"
        "📊 *Business reports:*\n"
        "_report_ — see daily revenue, top clients, "
        "busiest days, and profit trends\n\n"
        "🧾 *Tax reports:*\n"
        "_tax report_ — auto-generated for FIRS filing\n\n"
        "🎨 *Brand your invoices:*\n"
        "Upload your salon logo at suoops.com → Settings.\n\n"
        "👥 *Your team:*\n"
        "Staff can invoice from their own WhatsApp. "
        "You'll see everything on the dashboard.\n\n"
        "🖨️ *Print & share invoices:*\n"
        "Every invoice generates a professional PDF. "
        "Download it, print it, or send it directly to "
        "your clients via WhatsApp or email.\n\n"
        "🌐 *Dashboard:* suoops.com — analytics, inventory & more\n\n"
        "Need help? Just reply *help* 🙂"
    ),
    "retail_shop": (
        "🛍️ *Welcome to SuoOps, {name}!*\n\n"
        "Your shop *{business}* is all set with Pro features "
        "including full inventory management. "
        "Here's everything you can do:\n\n"
        "📱 *Invoice a customer:*\n"
        "_invoice Joy 08012345678, 10000 shoes, 5000 bag_\n\n"
        "💰 *Check who owes you:*\n"
        "_owed_\n"
        "→ Auto-reminders chase payments for you\n\n"
        "📦 *Track expenses:*\n"
        "_expense: 100000 new stock from supplier_\n\n"
        "🛒 *Inventory & stock management:*\n"
        "This is big for retail! At suoops.com → Products:\n"
        "• Add all your products with prices\n"
        "• Set stock quantities & reorder levels\n"
        "• Get *low-stock alerts* before you run out\n"
        "• Track suppliers & purchase history\n"
        "Reply _products_ to browse your catalog from WhatsApp.\n\n"
        "📊 *Business reports & analytics:*\n"
        "_report_ — revenue, top-selling items, "
        "customer insights, cash position\n\n"
        "🧾 *Tax reports:*\n"
        "_tax report_ — auto-generated for FIRS compliance\n\n"
        "🎨 *Brand your invoices:*\n"
        "Upload your shop logo at suoops.com → Settings. "
        "Professional branded PDFs for every sale.\n\n"
        "👥 *Your team:*\n"
        "Staff get invite emails and can invoice from their "
        "own WhatsApp — you'll see who sold what.\n\n"
        "🖨️ *Print & share invoices:*\n"
        "Every invoice generates a professional PDF. "
        "Download it, print it, or send it directly to "
        "your customers via WhatsApp or email.\n\n"
        "🌐 *Dashboard:* suoops.com — full analytics, "
        "inventory tracking, customer management\n\n"
        "Need help? Reply *help* 🙂"
    ),
    "services_freelance": (
        "💼 *Welcome to SuoOps, {name}!*\n\n"
        "*{business}* is set up with Pro features. "
        "Here's everything you can do:\n\n"
        "📱 *Create an invoice:*\n"
        "_invoice Client Name 08012345678, 150000 web design_\n\n"
        "💰 *Follow up on payments:*\n"
        "_owed_\n"
        "→ SuoOps auto-reminds clients who haven't paid\n\n"
        "📦 *Log project expenses:*\n"
        "_expense: 20000 hosting_\n\n"
        "🛒 *Service catalog:*\n"
        "List your services with standard rates at "
        "suoops.com → Products. Makes invoicing faster — "
        "just pick from your catalog.\n"
        "Reply _products_ to browse.\n\n"
        "📊 *Business reports & analytics:*\n"
        "_report_ — revenue trends, top clients, "
        "outstanding payments, cash flow\n\n"
        "🧾 *Tax reports:*\n"
        "_tax report_ — auto-generated for FIRS filing. "
        "Tracks your assessable profit.\n\n"
        "🎨 *Brand your invoices:*\n"
        "Upload your logo at suoops.com → Settings. "
        "Professional PDFs with your branding.\n\n"
        "🖨️ *Print & share invoices:*\n"
        "Every invoice generates a professional PDF. "
        "Download it, print it, or send it directly to "
        "your clients via WhatsApp or email.\n\n"
        "🌐 *Dashboard:* suoops.com — analytics, "
        "client management, financial overview\n\n"
        "Need help? Reply *help* anytime 🙂"
    ),
    "general": (
        "🎉 *Welcome to SuoOps, {name}!*\n\n"
        "*{business}* is all set up with Pro features. "
        "Here's everything you can do:\n\n"
        "📱 *Create an invoice:*\n"
        "_invoice Customer Name Phone, Amount Item_\n"
        "Example: _invoice Chidi 08012345678, 5000 wig_\n\n"
        "💰 *Check unpaid invoices:*\n"
        "_owed_\n"
        "→ Auto-reminders chase payments for you\n\n"
        "📦 *Track expenses:*\n"
        "_expense: 5000 transport_\n\n"
        "🛒 *Product catalog & inventory:*\n"
        "Add your products/services at suoops.com → Products. "
        "Track stock, set reorder alerts, manage suppliers.\n"
        "Reply _products_ to browse from WhatsApp.\n\n"
        "📊 *Business reports & analytics:*\n"
        "_report_ — revenue, customer insights, "
        "cash position, profit trends\n\n"
        "🧾 *Tax reports:*\n"
        "_tax report_ — auto-generated for FIRS compliance\n\n"
        "🎨 *Brand your invoices:*\n"
        "Upload your logo at suoops.com → Settings.\n\n"
        "👥 *Your team:*\n"
        "Team members will get invite emails. "
        "Each person invoices from their own WhatsApp.\n\n"
        "🖨️ *Print & share invoices:*\n"
        "Every invoice generates a professional PDF. "
        "Download it, print it, or send it directly to "
        "your customers via WhatsApp or email.\n\n"
        "🌐 *Dashboard:* suoops.com — full business "
        "management, analytics & more\n\n"
        "Need help? Reply *help* 🙂"
    ),
}


class SMEOnboardPayload(BaseModel):
    phone: str  # Business owner phone (Nigerian format)
    name: str
    business_name: str
    business_type: str = "general"  # bar_restaurant, salon_beauty, retail_shop, services_freelance, general
    staff_emails: list[str] = []  # up to 3 team member emails
    notes: str | None = None


class SMEOnboardResult(BaseModel):
    user_id: int
    is_new_user: bool
    wallet_credited: bool
    team_created: bool
    invites_sent: int
    whatsapp_sent: bool
    message: str


@router.post("/sme-onboard", response_model=SMEOnboardResult, status_code=201)
def onboard_sme(
    payload: SMEOnboardPayload,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> Any:
    """
    Concierge onboard an SME business.

    1. Creates or finds the business owner's account
    2. Credits their prepaid invoice wallet (all features are free)
    3. Creates a team and invites staff members
    4. Sends a tailored WhatsApp onboarding message
    """
    from app.utils.phone_utils import normalize_phone

    log_audit_event(
        "admin.sme_onboard",
        user_id=admin_user.id,
        phone=payload.phone,
        business=payload.business_name,
    )

    # ── 1. Normalize phone and find/create user ──────────────────
    phone = normalize_phone(payload.phone)

    user = db.query(models.User).filter(models.User.phone == phone).first()
    is_new = False

    if not user:
        user = models.User(
            name=payload.name,
            business_name=payload.business_name,
            phone=phone,
            phone_verified=True,
            signup_source="admin_onboard",
            invoice_balance=10,  # starter balance for concierge onboard
        )
        user.last_login = dt.datetime.now(dt.timezone.utc)
        db.add(user)
        db.commit()
        db.refresh(user)
        is_new = True
        logger.info("Created user %s for SME onboard: %s", user.id, payload.business_name)
    else:
        # Update business name if not set
        if not user.business_name and payload.business_name:
            user.business_name = payload.business_name
        if not user.name or user.name == phone:
            user.name = payload.name

    # ── 2. Credit the prepaid wallet (all features are free) ──
    # Give concierge-onboarded businesses a starter wallet (₦500) so they can
    # send invoices right away. Everything else is free under the 3% model.
    CONCIERGE_WALLET_KOBO = 50000  # ₦500
    wallet_credited = False
    if int(getattr(user, "wallet_balance_kobo", 0) or 0) < CONCIERGE_WALLET_KOBO:
        user.wallet_balance_kobo = CONCIERGE_WALLET_KOBO
        wallet_credited = True

    db.commit()

    # ── 3. Create team + invite staff ────────────────────────────
    team_created = False
    invites_sent = 0

    if payload.staff_emails:
        from app.models.team_models import Team, TeamInvitation, InvitationStatus

        # Create team if user doesn't have one
        team = db.query(Team).filter(Team.admin_user_id == user.id).first()
        if not team:
            team = Team(
                name=payload.business_name or f"{payload.name}'s Team",
                admin_user_id=user.id,
                max_members=max(3, len(payload.staff_emails)),
            )
            db.add(team)
            db.commit()
            db.refresh(team)
            team_created = True

        # Send invites (skip duplicates)
        for email in payload.staff_emails[:5]:  # cap at 5
            email = email.strip().lower()
            if not email:
                continue
            # Skip if already invited
            existing = db.query(TeamInvitation).filter(
                TeamInvitation.team_id == team.id,
                TeamInvitation.email == email,
                TeamInvitation.status == InvitationStatus.PENDING,
            ).first()
            if existing:
                continue

            import secrets
            invitation = TeamInvitation(
                team_id=team.id,
                email=email,
                token=secrets.token_urlsafe(32),
                invited_by_user_id=user.id,
                expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7),
            )
            db.add(invitation)
            db.commit()
            db.refresh(invitation)

            # Send invite email
            try:
                from app.utils.smtp import send_smtp_email
                invite_url = f"https://support.suoops.com/admin/accept-invite?token={invitation.token}"
                subject = f"You're invited to join {payload.business_name} on SuoOps"
                body = (
                    f"Hi,\n\n"
                    f"{payload.name} has invited you to join *{payload.business_name}* on SuoOps.\n\n"
                    f"SuoOps helps your team create professional invoices, "
                    f"track payments, and manage expenses — all from WhatsApp.\n\n"
                    f"Join the team: {invite_url}\n\n"
                    f"This link expires in 7 days.\n\n"
                    f"— The SuoOps Team"
                )
                send_smtp_email(email, subject, None, body)
                invites_sent += 1
            except Exception as e:
                logger.warning("Failed to send invite to %s: %s", email, e)

    # ── 4. Send tailored WhatsApp onboarding message ─────────────
    wa_sent = False
    try:
        from app.core.whatsapp import get_whatsapp_client
        from app.core.config import settings

        client = get_whatsapp_client()

        # Send welcome template first (works outside 24h window)
        tpl = settings.WHATSAPP_TEMPLATE_ACTIVATION_WELCOME
        if tpl:
            first_name = payload.name.split()[0]
            lang = settings.WHATSAPP_TEMPLATE_LANGUAGE or "en"
            components = [{"type": "body", "parameters": [{"type": "text", "text": first_name}]}]
            client.send_template(phone, tpl, lang, components)

        # Then send the tailored business-type message
        import time
        time.sleep(2)
        biz_type = payload.business_type if payload.business_type in _SME_MESSAGES else "general"
        msg = _SME_MESSAGES[biz_type].format(
            name=payload.name.split()[0],
            business=payload.business_name,
        )
        if client.send_text(phone, msg):
            wa_sent = True
    except Exception as e:
        logger.warning("SME onboard WhatsApp failed for %s: %s", phone, e)

    summary_parts = []
    if is_new:
        summary_parts.append("account created")
    if wallet_credited:
        summary_parts.append("wallet credited")
    if team_created:
        summary_parts.append("team created")
    if invites_sent:
        summary_parts.append(f"{invites_sent} invites sent")
    if wa_sent:
        summary_parts.append("WhatsApp sent")

    return SMEOnboardResult(
        user_id=user.id,
        is_new_user=is_new,
        wallet_credited=wallet_credited,
        team_created=team_created,
        invites_sent=invites_sent,
        whatsapp_sent=wa_sent,
        message=", ".join(summary_parts) or "User already onboarded",
    )


# ============================================================================
# Platform Metrics
# ============================================================================

class TopUpBuyerInfo(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    business_name: str | None
    wallet_balance_naira: float
    total_top_ups: int
    last_purchase_date: str | None

    model_config = ConfigDict(from_attributes=True)


class PlatformMetrics(BaseModel):
    total_invoices: int
    paid_invoices: int
    pending_invoices: int
    cancelled_invoices: int
    total_revenue_amount: float
    total_expense_amount: float
    invoices_today: int
    invoices_this_week: int
    invoices_this_month: int
    total_users: int
    online_payments_enabled: int
    storefronts_enabled: int
    storefronts_live: int  # actually visible in the public global-search directory
    monetized_users: int  # distinct businesses paying Suoops (online payments or top-ups)
    commission_this_month: float  # Suoops earnings (3% fees) this month, in Naira
    commission_wallet_this_month: float  # from manual invoicing (wallet debits)
    commission_online_this_month: float  # from online/Paystack payments
    total_customers: int
    top_up_buyers: list[TopUpBuyerInfo]


@router.get("/metrics", response_model=PlatformMetrics)
def get_platform_metrics(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """Get platform-wide metrics for monitoring."""
    from app.models.models import Customer, Invoice

    log_audit_event("admin.metrics", user_id=admin_user.id)
    
    now = dt.datetime.now(dt.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - dt.timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    
    # Invoice counts
    total_invoices = db.query(Invoice).count()
    paid = db.query(Invoice).filter(Invoice.status == "paid").count()
    pending = db.query(Invoice).filter(Invoice.status == "pending").count()
    cancelled = db.query(Invoice).filter(Invoice.status == "cancelled").count()
    
    # Revenue and expense totals
    revenue_sum = db.query(func.sum(Invoice.amount)).filter(
        Invoice.invoice_type == "revenue",
        Invoice.status == "paid"
    ).scalar() or 0
    
    expense_sum = db.query(func.sum(Invoice.amount)).filter(
        Invoice.invoice_type == "expense"
    ).scalar() or 0
    
    # Time-based invoices
    invoices_today = db.query(Invoice).filter(Invoice.created_at >= today_start).count()
    invoices_week = db.query(Invoice).filter(Invoice.created_at >= week_start).count()
    invoices_month = db.query(Invoice).filter(Invoice.created_at >= month_start).count()

    # Users + commission-model adoption
    total_users = db.query(models.User).count()
    online_payments_enabled = db.query(models.User).filter(
        models.User.paystack_subaccount_active.is_(True)
    ).count()
    storefronts_enabled = db.query(models.User).filter(
        models.User.storefront_enabled.is_(True)
    ).count()
    # "Live" = passes the same trust gate as the public marketplace (logo +
    # online payments + active product + not suspended), i.e. shoppers can
    # actually find it in global search — not merely toggled on.
    from app.api.routes_storefront import count_live_storefronts
    storefronts_live = count_live_storefronts(db)

    # Commission earned this month, split by stream so both are auditable:
    #  - Wallet: the flat 3% is debited from the prepaid wallet at CREATION for
    #    every non-storefront revenue invoice (manual invoices AND online-enabled
    #    businesses' invoices — both charge the wallet). Count by created_at.
    #  - Online: storefront orders never touch the wallet; Paystack collects the
    #    3% when the customer PAYS. Count storefront orders by paid_at (paid only).
    from sqlalchemy import or_

    from app.utils.feature_gate import platform_fee_kobo
    wallet_amounts = db.query(Invoice.amount).filter(
        Invoice.invoice_type == "revenue",
        Invoice.created_at >= month_start,
        or_(Invoice.channel != "storefront", Invoice.channel.is_(None)),
    ).all()
    commission_wallet_kobo = sum(platform_fee_kobo(a) for (a,) in wallet_amounts)

    online_amounts = db.query(Invoice.amount).filter(
        Invoice.invoice_type == "revenue",
        Invoice.channel == "storefront",
        Invoice.status == "paid",
        Invoice.paid_at >= month_start,
    ).all()
    commission_online_kobo = sum(platform_fee_kobo(a) for (a,) in online_amounts)

    commission_wallet_this_month = commission_wallet_kobo / 100
    commission_online_this_month = commission_online_kobo / 100
    commission_this_month = commission_wallet_this_month + commission_online_this_month

    # Customers
    total_customers = db.query(Customer).count()

    # Wallet top-up buyers (top-ups still use the legacy INVPACK- reference).
    top_up_rows = db.query(
        models.User,
        func.count(PaymentTransaction.id).label("topup_count"),
        func.max(PaymentTransaction.created_at).label("last_purchase"),
    ).join(
        PaymentTransaction, PaymentTransaction.user_id == models.User.id
    ).filter(
        PaymentTransaction.reference.like("INVPACK-%"),
        PaymentTransaction.status == PaymentStatus.SUCCESS,
    ).group_by(models.User.id).order_by(
        desc(func.max(PaymentTransaction.created_at))
    ).limit(ADMIN_LIST_CAP).all()

    top_up_buyers_list: list[TopUpBuyerInfo] = []
    for user, topup_count, last_purchase in top_up_rows:
        top_up_buyers_list.append(TopUpBuyerInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            business_name=user.business_name,
            wallet_balance_naira=int(getattr(user, "wallet_balance_kobo", 0) or 0) / 100,
            total_top_ups=topup_count,
            last_purchase_date=last_purchase.isoformat() if last_purchase else None,
        ))

    # Monetized businesses = distinct users who actually pay Suoops: they either
    # enabled online payments (commission on each order) OR funded their wallet
    # via a top-up. Distinct so the two groups aren't double-counted.
    monetized_users = db.query(func.count(func.distinct(models.User.id))).filter(
        or_(
            models.User.paystack_subaccount_active.is_(True),
            models.User.id.in_(
                db.query(PaymentTransaction.user_id).filter(
                    PaymentTransaction.reference.like("INVPACK-%"),
                    PaymentTransaction.status == PaymentStatus.SUCCESS,
                )
            ),
        )
    ).scalar() or 0

    return PlatformMetrics(
        total_invoices=total_invoices,
        paid_invoices=paid,
        pending_invoices=pending,
        cancelled_invoices=cancelled,
        total_revenue_amount=float(revenue_sum),
        total_expense_amount=float(expense_sum),
        invoices_today=invoices_today,
        invoices_this_week=invoices_week,
        invoices_this_month=invoices_month,
        total_users=total_users,
        online_payments_enabled=online_payments_enabled,
        storefronts_enabled=storefronts_enabled,
        storefronts_live=storefronts_live,
        monetized_users=monetized_users,
        commission_this_month=commission_this_month,
        commission_wallet_this_month=commission_wallet_this_month,
        commission_online_this_month=commission_online_this_month,
        total_customers=total_customers,
        top_up_buyers=top_up_buyers_list,
    )


# =============================================================================
# GROWTH METRICS — Commission, Churn, Activation, Collection Rate, Trends
# =============================================================================

class MonthlyDataPoint(BaseModel):
    month: str  # "2026-01"
    value: float

class ActivationFunnel(BaseModel):
    total_signups: int
    created_first_invoice: int
    received_first_payment: int
    enabled_online_payments: int

class GrowthMetrics(BaseModel):
    # Revenue (Suoops commission — the flat 3% earned)
    commission_month: float  # Commission earned this month, in Naira
    commission_trend: list[MonthlyDataPoint]  # Last 6 months
    commission_run_rate: float  # Annualized (this month × 12)
    # Churn (activity-based: active last month, inactive this month)
    churned_users: int
    churn_rate: float  # % of last month's active businesses now inactive
    # Activation
    activation_funnel: ActivationFunnel
    # Collection
    collection_rate: float  # % of invoices that get paid
    avg_days_to_payment: float | None  # Average days from created → paid
    # Growth trends
    user_growth: list[MonthlyDataPoint]  # New signups per month
    invoice_growth: list[MonthlyDataPoint]  # Invoices created per month
    gmv_growth: list[MonthlyDataPoint]  # Paid payment volume per month
    # Engagement
    avg_invoices_per_user: float
    power_users: int  # Users with 10+ invoices this month
    zero_invoice_users: int  # Signed up but never created an invoice
    whatsapp_users: int  # Users with verified WhatsApp phone
    email_only_users: int  # Users without WhatsApp (email only)


@router.get("/metrics/growth", response_model=GrowthMetrics)
def get_growth_metrics(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """Get business growth metrics — commission, churn, activation funnel, trends."""
    from sqlalchemy import or_

    from app.models.models import Invoice
    from app.utils.feature_gate import platform_fee_kobo

    log_audit_event("admin.metrics.growth", user_id=admin_user.id)

    now = dt.datetime.now(dt.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    def _month_starts(count: int) -> list[dt.datetime]:
        """Return the first-of-month datetimes for the last `count` months (oldest first)."""
        starts: list[dt.datetime] = []
        cursor = month_start
        for _ in range(count):
            starts.append(cursor)
            cursor = (cursor - dt.timedelta(days=1)).replace(day=1)
        return list(reversed(starts))

    def _commission_between(start: dt.datetime, end: dt.datetime) -> float:
        """Commission (Naira) earned in [start, end): manual invoices charged at
        creation + storefront orders charged (via Paystack) when paid."""
        manual = db.query(Invoice.amount).filter(
            Invoice.invoice_type == "revenue",
            Invoice.created_at >= start,
            Invoice.created_at < end,
            or_(Invoice.channel != "storefront", Invoice.channel.is_(None)),
        ).all()
        online = db.query(Invoice.amount).filter(
            Invoice.invoice_type == "revenue",
            Invoice.channel == "storefront",
            Invoice.status == "paid",
            Invoice.paid_at >= start,
            Invoice.paid_at < end,
        ).all()
        return (
            sum(platform_fee_kobo(a) for (a,) in manual)
            + sum(platform_fee_kobo(a) for (a,) in online)
        ) / 100

    # ── Commission (Suoops earnings this month) ──
    next_month = (month_start + dt.timedelta(days=32)).replace(day=1)
    commission_month = _commission_between(month_start, next_month)
    commission_run_rate = commission_month * 12

    # ── Commission Trend (last 6 months) ──
    commission_trend: list[MonthlyDataPoint] = []
    for m_start in _month_starts(6):
        m_end = (m_start + dt.timedelta(days=32)).replace(day=1)
        commission_trend.append(MonthlyDataPoint(
            month=m_start.strftime("%Y-%m"),
            value=_commission_between(m_start, m_end),
        ))

    # ── Churn (activity-based) ──
    # Businesses that created a revenue invoice last month but none this month.
    prev_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
    active_prev = {
        r[0] for r in db.query(func.distinct(Invoice.issuer_id)).filter(
            Invoice.invoice_type == "revenue",
            Invoice.created_at >= prev_month_start,
            Invoice.created_at < month_start,
        ).all()
    }
    active_now = {
        r[0] for r in db.query(func.distinct(Invoice.issuer_id)).filter(
            Invoice.invoice_type == "revenue",
            Invoice.created_at >= month_start,
        ).all()
    }
    churned = len(active_prev - active_now)
    churn_rate = (churned / len(active_prev) * 100) if active_prev else 0

    # ── Activation Funnel ──
    total_signups = db.query(models.User).count()

    # Users who created at least 1 invoice
    users_with_invoice = db.query(
        func.count(func.distinct(Invoice.issuer_id))
    ).scalar() or 0

    # Users who received at least 1 payment
    users_with_payment = db.query(
        func.count(func.distinct(Invoice.issuer_id))
    ).filter(Invoice.status == "paid").scalar() or 0

    # Users who turned on online payments (Paystack subaccount active)
    enabled_online = db.query(models.User).filter(
        models.User.paystack_subaccount_active.is_(True)
    ).count()

    funnel = ActivationFunnel(
        total_signups=total_signups,
        created_first_invoice=users_with_invoice,
        received_first_payment=users_with_payment,
        enabled_online_payments=enabled_online,
    )

    # ── Collection Rate ──
    total_revenue_invoices = db.query(Invoice).filter(
        Invoice.invoice_type == "revenue"
    ).count()
    paid_revenue_invoices = db.query(Invoice).filter(
        Invoice.invoice_type == "revenue",
        Invoice.status == "paid"
    ).count()
    collection_rate = (
        (paid_revenue_invoices / total_revenue_invoices * 100)
        if total_revenue_invoices > 0 else 0
    )

    # Average days to payment
    avg_days_raw = db.query(
        func.avg(
            func.extract("epoch", Invoice.paid_at - Invoice.created_at) / 86400
        )
    ).filter(
        Invoice.status == "paid",
        Invoice.paid_at.isnot(None),
    ).scalar()
    avg_days_to_payment = round(float(avg_days_raw), 1) if avg_days_raw else None

    # ── Growth Trends (last 6 months) ──
    user_growth: list[MonthlyDataPoint] = []
    invoice_growth: list[MonthlyDataPoint] = []
    gmv_growth: list[MonthlyDataPoint] = []

    for i in range(5, -1, -1):
        m_start = (month_start - dt.timedelta(days=1)).replace(day=1)
        for _ in range(i):
            m_start = (m_start - dt.timedelta(days=1)).replace(day=1)
        if i == 0:
            m_start = month_start
        m_end = (m_start + dt.timedelta(days=32)).replace(day=1)
        label = m_start.strftime("%Y-%m")

        new_users = db.query(models.User).filter(
            models.User.created_at >= m_start,
            models.User.created_at < m_end,
        ).count()
        user_growth.append(MonthlyDataPoint(month=label, value=new_users))

        new_invoices = db.query(Invoice).filter(
            Invoice.created_at >= m_start,
            Invoice.created_at < m_end,
        ).count()
        invoice_growth.append(MonthlyDataPoint(month=label, value=new_invoices))

        month_rev = db.query(func.sum(Invoice.amount)).filter(
            Invoice.invoice_type == "revenue",
            Invoice.status == "paid",
            Invoice.paid_at >= m_start,
            Invoice.paid_at < m_end,
        ).scalar() or 0
        gmv_growth.append(MonthlyDataPoint(month=label, value=float(month_rev)))

    # ── Engagement ──
    invoice_counts_sq = db.query(
        func.count(Invoice.id).label("cnt")
    ).group_by(Invoice.issuer_id).subquery()
    avg_invoices = db.query(func.avg(invoice_counts_sq.c.cnt)).scalar()
    avg_invoices_per_user = round(float(avg_invoices), 1) if avg_invoices else 0

    power_user_sq = db.query(
        Invoice.issuer_id
    ).filter(
        Invoice.created_at >= month_start
    ).group_by(Invoice.issuer_id).having(func.count(Invoice.id) >= 10).subquery()
    power_users = db.query(func.count()).select_from(power_user_sq).scalar() or 0

    users_with_any_invoice = db.query(Invoice.issuer_id).distinct().subquery()
    zero_invoice = db.query(models.User).filter(
        ~models.User.id.in_(db.query(users_with_any_invoice))
    ).count()

    # ── Channel Segmentation ──
    whatsapp_users = db.query(models.User).filter(
        models.User.phone_verified.is_(True),
        models.User.phone != None,  # noqa: E711
    ).count()
    email_only_users = total_signups - whatsapp_users

    return GrowthMetrics(
        commission_month=commission_month,
        commission_trend=commission_trend,
        commission_run_rate=commission_run_rate,
        churned_users=churned,
        churn_rate=round(churn_rate, 1),
        activation_funnel=funnel,
        collection_rate=round(collection_rate, 1),
        avg_days_to_payment=avg_days_to_payment,
        user_growth=user_growth,
        invoice_growth=invoice_growth,
        gmv_growth=gmv_growth,
        avg_invoices_per_user=avg_invoices_per_user,
        power_users=power_users,
        zero_invoice_users=zero_invoice,
        whatsapp_users=whatsapp_users,
        email_only_users=email_only_users,
    )


# =============================================================================
# ZERO-INVOICE DIAGNOSTIC — Why are users not creating invoices?
# =============================================================================


class ZeroInvoiceCohort(BaseModel):
    """A group of zero-invoice users sharing a trait."""
    label: str
    count: int
    pct: float  # % of total zero-invoice users


class ZeroInvoiceUser(BaseModel):
    id: int
    name: str | None
    phone: str | None
    email: str | None
    phone_verified: bool
    created_at: str
    last_login: str | None
    has_business_name: bool
    has_bank_details: bool
    has_logo: bool
    days_since_signup: int
    login_count_bucket: str  # "never", "once", "2-5", "6+"
    signup_source: str | None


class ZeroInvoiceDiagnostic(BaseModel):
    total_zero_invoice: int
    total_signups: int
    drop_off_rate: float  # % of signups that are zero-invoice

    # Engagement buckets
    never_logged_back: ZeroInvoiceCohort  # last_login is None or == created_at
    logged_in_once: ZeroInvoiceCohort  # came back once but didn't create
    logged_in_multiple: ZeroInvoiceCohort  # came back 2+ times

    # Channel
    whatsapp_verified: ZeroInvoiceCohort
    email_only: ZeroInvoiceCohort

    # Profile completeness
    has_business_name: ZeroInvoiceCohort
    has_bank_details: ZeroInvoiceCohort

    # Signup age
    signed_up_today: ZeroInvoiceCohort  # < 24h — still in grace period
    signed_up_1_3_days: ZeroInvoiceCohort
    signed_up_4_7_days: ZeroInvoiceCohort
    signed_up_8_14_days: ZeroInvoiceCohort
    signed_up_15_30_days: ZeroInvoiceCohort
    signed_up_over_30_days: ZeroInvoiceCohort

    # Weekly signup → activation trend (last 8 weeks)
    weekly_signup_vs_activation: list[dict]

    # Signup source attribution
    source_breakdown: list[ZeroInvoiceCohort]  # per signup_source
    source_activation_rates: list[dict]  # source + signups + activated + rate

    # Sample users for manual outreach
    recent_zero_invoice_users: list[ZeroInvoiceUser]


@router.get("/metrics/zero-invoice-diagnostic", response_model=ZeroInvoiceDiagnostic)
def get_zero_invoice_diagnostic(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    sample_limit: int = Query(default=20, le=50),
) -> Any:
    """Diagnose why users sign up but never create an invoice."""
    from app.models.models import Invoice

    log_audit_event("admin.metrics.zero_invoice_diagnostic", user_id=admin_user.id)

    now = dt.datetime.now(dt.timezone.utc)

    # ── Get all zero-invoice user IDs ──
    users_with_invoices = db.query(Invoice.issuer_id).distinct().subquery()
    zero_q = db.query(models.User).filter(
        ~models.User.id.in_(db.query(users_with_invoices))
    )
    zero_users = zero_q.all()
    total_zero = len(zero_users)
    total_signups = db.query(models.User).count()
    drop_off = (total_zero / total_signups * 100) if total_signups > 0 else 0

    def cohort(label: str, count: int) -> ZeroInvoiceCohort:
        return ZeroInvoiceCohort(
            label=label,
            count=count,
            pct=round(count / total_zero * 100, 1) if total_zero > 0 else 0,
        )

    # ── Engagement buckets ──
    never_logged = 0
    logged_once = 0
    logged_multi = 0
    for u in zero_users:
        if u.last_login is None:
            never_logged += 1
        else:
            # Compare last_login to created_at — if within 5 min, treat as "signup session only"
            created = u.created_at.replace(tzinfo=dt.timezone.utc) if u.created_at.tzinfo is None else u.created_at
            last = u.last_login.replace(tzinfo=dt.timezone.utc) if u.last_login.tzinfo is None else u.last_login
            diff_minutes = (last - created).total_seconds() / 60
            if diff_minutes < 5:
                never_logged += 1
            elif diff_minutes < 1440:  # < 24h = came back once
                logged_once += 1
            else:
                logged_multi += 1

    # ── Channel ──
    wa_verified = sum(1 for u in zero_users if u.phone_verified and u.phone)
    email_only_count = total_zero - wa_verified

    # ── Profile completeness ──
    has_biz = sum(1 for u in zero_users if u.business_name)
    has_bank = sum(1 for u in zero_users if u.bank_name and u.account_number)

    # ── Signup age buckets ──
    age_buckets = {"today": 0, "1_3": 0, "4_7": 0, "8_14": 0, "15_30": 0, "30+": 0}
    for u in zero_users:
        created = u.created_at.replace(tzinfo=dt.timezone.utc) if u.created_at.tzinfo is None else u.created_at
        days = (now - created).days
        if days < 1:
            age_buckets["today"] += 1
        elif days <= 3:
            age_buckets["1_3"] += 1
        elif days <= 7:
            age_buckets["4_7"] += 1
        elif days <= 14:
            age_buckets["8_14"] += 1
        elif days <= 30:
            age_buckets["15_30"] += 1
        else:
            age_buckets["30+"] += 1

    # ── Weekly signup vs activation trend (last 8 weeks) ──
    weekly_trend = []
    for w in range(7, -1, -1):
        week_start = now - dt.timedelta(weeks=w + 1)
        week_end = now - dt.timedelta(weeks=w)
        week_label = week_start.strftime("%b %d")

        signups_in_week = db.query(models.User).filter(
            models.User.created_at >= week_start,
            models.User.created_at < week_end,
        ).count()

        activated_in_week = db.query(
            func.count(func.distinct(Invoice.issuer_id))
        ).join(
            models.User, models.User.id == Invoice.issuer_id
        ).filter(
            models.User.created_at >= week_start,
            models.User.created_at < week_end,
        ).scalar() or 0

        weekly_trend.append({
            "week": week_label,
            "signups": signups_in_week,
            "activated": activated_in_week,
            "activation_rate": round(
                activated_in_week / signups_in_week * 100, 1
            ) if signups_in_week > 0 else 0,
        })

    # ── Sample users for outreach ──
    sample_users = zero_q.order_by(models.User.created_at.desc()).limit(sample_limit).all()

    def classify_login(u: models.User) -> str:
        if u.last_login is None:
            return "never"
        created = u.created_at.replace(tzinfo=dt.timezone.utc) if u.created_at.tzinfo is None else u.created_at
        last = u.last_login.replace(tzinfo=dt.timezone.utc) if u.last_login.tzinfo is None else u.last_login
        diff_minutes = (last - created).total_seconds() / 60
        if diff_minutes < 5:
            return "never"
        elif diff_minutes < 1440:
            return "once"
        else:
            return "2+"

    recent_users = [
        ZeroInvoiceUser(
            id=u.id,
            name=u.name,
            phone=u.phone,
            email=u.email,
            phone_verified=u.phone_verified,
            created_at=u.created_at.isoformat() if u.created_at else "",
            last_login=u.last_login.isoformat() if u.last_login else None,
            has_business_name=bool(u.business_name),
            has_bank_details=bool(u.bank_name and u.account_number),
            has_logo=bool(u.logo_url),
            days_since_signup=(now - (u.created_at.replace(tzinfo=dt.timezone.utc) if u.created_at.tzinfo is None else u.created_at)).days,
            login_count_bucket=classify_login(u),
            signup_source=getattr(u, "signup_source", None),
        )
        for u in sample_users
    ]

    # ── Signup source breakdown ──
    source_counts: dict[str, int] = {}
    for u in zero_users:
        src = getattr(u, "signup_source", None) or "unknown"
        source_counts[src] = source_counts.get(src, 0) + 1

    source_breakdown = sorted(
        [cohort(src, cnt) for src, cnt in source_counts.items()],
        key=lambda c: c.count,
        reverse=True,
    )

    # ── Source activation rates (all users, not just zero-invoice) ──
    # Compare signup_source across ALL users to see which channels convert
    all_sources = db.query(
        models.User.signup_source,
        func.count(models.User.id).label("total"),
    ).group_by(models.User.signup_source).all()

    activated_by_source = db.query(
        models.User.signup_source,
        func.count(func.distinct(Invoice.issuer_id)).label("activated"),
    ).join(
        Invoice, Invoice.issuer_id == models.User.id
    ).group_by(models.User.signup_source).all()

    activated_map = {row.signup_source: row.activated for row in activated_by_source}
    source_activation_rates = []
    for row in all_sources:
        src = row.signup_source or "unknown"
        total = row.total
        activated = activated_map.get(row.signup_source, 0)
        source_activation_rates.append({
            "source": src,
            "signups": total,
            "activated": activated,
            "activation_rate": round(activated / total * 100, 1) if total > 0 else 0,
        })
    source_activation_rates.sort(key=lambda x: x["signups"], reverse=True)

    return ZeroInvoiceDiagnostic(
        total_zero_invoice=total_zero,
        total_signups=total_signups,
        drop_off_rate=round(drop_off, 1),
        never_logged_back=cohort("Never logged back in", never_logged),
        logged_in_once=cohort("Logged in once, didn't create", logged_once),
        logged_in_multiple=cohort("Logged in 2+ times, still didn't create", logged_multi),
        whatsapp_verified=cohort("WhatsApp verified", wa_verified),
        email_only=cohort("Email only", email_only_count),
        has_business_name=cohort("Set a business name", has_biz),
        has_bank_details=cohort("Added bank details", has_bank),
        signed_up_today=cohort("< 24 hours ago", age_buckets["today"]),
        signed_up_1_3_days=cohort("1–3 days ago", age_buckets["1_3"]),
        signed_up_4_7_days=cohort("4–7 days ago", age_buckets["4_7"]),
        signed_up_8_14_days=cohort("8–14 days ago", age_buckets["8_14"]),
        signed_up_15_30_days=cohort("15–30 days ago", age_buckets["15_30"]),
        signed_up_over_30_days=cohort("30+ days ago", age_buckets["30+"]),
        weekly_signup_vs_activation=weekly_trend,
        source_breakdown=source_breakdown,
        source_activation_rates=source_activation_rates,
        recent_zero_invoice_users=recent_users,
    )


# =============================================================================
# BUSINESS INTELLIGENCE — Per-business health for admin
# =============================================================================

class BusinessHealthItem(BaseModel):
    """Per-business health snapshot."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    business_name: str | None
    phone: str | None
    email: str | None
    plan: str
    created_at: str
    last_login: str | None

    # Subscription
    subscription_started_at: str | None
    subscription_expires_at: str | None
    subscription_status: str  # active, expired, expiring_soon, free
    days_until_expiry: int | None
    invoice_balance: int

    # Revenue
    total_revenue: float
    total_expenses: float
    net_income: float
    invoices_total: int
    invoices_paid: int
    invoices_pending: int
    collection_rate: float

    # Activity
    customers_count: int
    invoices_this_month: int
    last_invoice_date: str | None
    days_since_last_invoice: int | None
    avg_invoice_value: float

    # Risk / Opportunity
    health_score: int  # 0-100
    risk_flags: list[str]


class BusinessListResponse(BaseModel):
    businesses: list[BusinessHealthItem]
    total: int
    page: int
    page_size: int


# ─── Activity Analytics ─────────────────────────────────────────


class ChannelBreakdown(BaseModel):
    whatsapp: int = 0
    dashboard: int = 0


class PeriodActivity(BaseModel):
    total: int = 0
    by_channel: ChannelBreakdown = ChannelBreakdown()


class DailyPoint(BaseModel):
    date: str
    total: int = 0
    whatsapp: int = 0
    dashboard: int = 0


class ActivityAnalytics(BaseModel):
    today: PeriodActivity
    yesterday: PeriodActivity
    this_week: PeriodActivity
    last_week: PeriodActivity
    this_month: PeriodActivity
    last_month: PeriodActivity
    this_year: PeriodActivity

    # Active users (created ≥1 invoice in period)
    active_users_today: int = 0
    active_users_this_week: int = 0
    active_users_this_month: int = 0

    # Active user cohorts by account age
    new_active_users_today: int = 0
    returning_active_users_today: int = 0
    new_active_users_this_week: int = 0
    returning_active_users_this_week: int = 0
    new_active_users_this_month: int = 0
    returning_active_users_this_month: int = 0

    # Daily trend (last 30 days)
    daily_trend: list[DailyPoint] = []

    # Logins
    logins_today: int = 0
    logins_this_week: int = 0
    logins_this_month: int = 0


@router.get("/metrics/activity", response_model=ActivityAnalytics)
def get_activity_analytics(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> Any:
    """
    User activity analytics — daily/weekly/monthly invoice creation
    broken down by channel (WhatsApp vs dashboard vs email).
    """
    from sqlalchemy import case, distinct, func

    from app.models.models import Invoice

    log_audit_event("admin.metrics.activity", user_id=admin_user.id)

    now = dt.datetime.now(dt.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - dt.timedelta(days=1)
    week_start = today_start - dt.timedelta(days=today_start.weekday())
    last_week_start = week_start - dt.timedelta(days=7)
    month_start = today_start.replace(day=1)
    last_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
    year_start = today_start.replace(month=1, day=1)
    seven_days_ago = now - dt.timedelta(days=7)

    # Channel tracking was added June 14 2026; historical data is inaccurate.
    # Only surface channel breakdown for invoices created from that date onward.
    channel_cutoff = dt.datetime(2026, 6, 14, tzinfo=dt.timezone.utc)

    def _count_period(start: dt.datetime, end: dt.datetime) -> PeriodActivity:
        rows = (
            db.query(
                Invoice.channel,
                func.count(Invoice.id),
            )
            .filter(Invoice.created_at >= start, Invoice.created_at < end)
            .group_by(Invoice.channel)
            .all()
        )
        breakdown = ChannelBreakdown()
        total = 0
        for ch, cnt in rows:
            total += cnt
            # Only populate channel split for periods starting after the cutoff
            if start >= channel_cutoff:
                if ch == "whatsapp":
                    breakdown.whatsapp = cnt
                else:
                    breakdown.dashboard += cnt
        return PeriodActivity(total=total, by_channel=breakdown)

    today_act = _count_period(today_start, now)
    yesterday_act = _count_period(yesterday_start, today_start)
    this_week_act = _count_period(week_start, now)
    last_week_act = _count_period(last_week_start, week_start)
    this_month_act = _count_period(month_start, now)
    last_month_act = _count_period(last_month_start, month_start)
    this_year_act = _count_period(year_start, now)

    # Active unique users per period
    def _active_users(start: dt.datetime, end: dt.datetime) -> int:
        return (
            db.query(func.count(distinct(Invoice.issuer_id)))
            .filter(Invoice.created_at >= start, Invoice.created_at < end)
            .scalar()
        ) or 0

    active_today = _active_users(today_start, now)
    active_week = _active_users(week_start, now)
    active_month = _active_users(month_start, now)

    def _active_users_by_signup_age(start: dt.datetime, end: dt.datetime) -> tuple[int, int]:
        new_count = (
            db.query(func.count(distinct(Invoice.issuer_id)))
            .join(models.User, models.User.id == Invoice.issuer_id)
            .filter(
                Invoice.created_at >= start,
                Invoice.created_at < end,
                models.User.created_at >= seven_days_ago,
            )
            .scalar()
        ) or 0
        returning_count = (
            db.query(func.count(distinct(Invoice.issuer_id)))
            .join(models.User, models.User.id == Invoice.issuer_id)
            .filter(
                Invoice.created_at >= start,
                Invoice.created_at < end,
                models.User.created_at < seven_days_ago,
            )
            .scalar()
        ) or 0
        return new_count, returning_count

    new_today, returning_today = _active_users_by_signup_age(today_start, now)
    new_week, returning_week = _active_users_by_signup_age(week_start, now)
    new_month, returning_month = _active_users_by_signup_age(month_start, now)

    # Daily trend — last 30 days
    thirty_days_ago = today_start - dt.timedelta(days=30)
    daily_rows = (
        db.query(
            func.date(Invoice.created_at).label("day"),
            func.count(Invoice.id).label("total"),
            func.sum(case((Invoice.channel == "whatsapp", 1), else_=0)).label("wa"),
            func.sum(case((Invoice.channel == "dashboard", 1), else_=0)).label("dash"),
        )
        .filter(Invoice.created_at >= thirty_days_ago)
        .group_by(func.date(Invoice.created_at))
        .order_by(func.date(Invoice.created_at))
        .all()
    )
    daily_trend = [
        DailyPoint(
            date=str(r.day),
            total=r.total,
            # Only show channel split for days on/after the tracking cutoff
            whatsapp=(r.wa or 0) if r.day >= channel_cutoff.date() else 0,
            dashboard=(r.dash or 0) if r.day >= channel_cutoff.date() else 0,
        )
        for r in daily_rows
    ]

    # Logins (approximate via last_login timestamps)
    logins_today = (
        db.query(func.count(models.User.id))
        .filter(models.User.last_login >= today_start)
        .scalar()
    ) or 0
    logins_week = (
        db.query(func.count(models.User.id))
        .filter(models.User.last_login >= week_start)
        .scalar()
    ) or 0
    logins_month = (
        db.query(func.count(models.User.id))
        .filter(models.User.last_login >= month_start)
        .scalar()
    ) or 0

    return ActivityAnalytics(
        today=today_act,
        yesterday=yesterday_act,
        this_week=this_week_act,
        last_week=last_week_act,
        this_month=this_month_act,
        last_month=last_month_act,
        this_year=this_year_act,
        active_users_today=active_today,
        active_users_this_week=active_week,
        active_users_this_month=active_month,
        new_active_users_today=new_today,
        returning_active_users_today=returning_today,
        new_active_users_this_week=new_week,
        returning_active_users_this_week=returning_week,
        new_active_users_this_month=new_month,
        returning_active_users_this_month=returning_month,
        daily_trend=daily_trend,
        logins_today=logins_today,
        logins_this_week=logins_week,
        logins_this_month=logins_month,
    )


@router.get("/businesses", response_model=BusinessListResponse)
def get_business_intelligence(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    sort_by: str = Query("health_score", pattern="^(health_score|total_revenue|invoices_total|created_at|last_login|name|collection_rate)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    plan_filter: str | None = Query(None, pattern="^(free|starter|pro)$"),
    risk_filter: str | None = Query(None, pattern="^(at_risk|healthy|inactive|churned)$"),
    search: str | None = Query(None, max_length=100),
    _admin: Any = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Business-level intelligence — per-business health metrics."""
    from app.models.models import Invoice

    now = dt.datetime.now(dt.timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - dt.timedelta(days=30)

    # ── Base query: all registered users ──
    q = db.query(models.User)

    if plan_filter:
        plan_enum = {
            "free": SubscriptionPlan.FREE,
            "starter": SubscriptionPlan.FREE,  # Legacy: STARTER mapped to FREE
            "pro": SubscriptionPlan.PRO,
        }.get(plan_filter, SubscriptionPlan.FREE)
        q = q.filter(models.User.plan == plan_enum)

    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            (models.User.name.ilike(term))
            | (models.User.business_name.ilike(term))
            | (models.User.phone.ilike(term))
            | (models.User.email.ilike(term))
        )

    all_users = q.limit(ADMIN_LIST_CAP).all()

    # ── Pre-fetch aggregated invoice data per user ──
    inv_stats = (
        db.query(
            Invoice.issuer_id,
            func.count(Invoice.id).label("total"),
            func.count(case((Invoice.status == "paid", 1))).label("paid"),
            func.count(case((Invoice.status == "pending", 1))).label("pending"),
            func.sum(
                case((Invoice.invoice_type == "revenue", Invoice.amount), else_=0)
            ).label("revenue"),
            func.sum(
                case((Invoice.invoice_type == "expense", Invoice.amount), else_=0)
            ).label("expenses"),
            func.max(Invoice.created_at).label("last_invoice"),
            func.count(
                case(
                    (Invoice.created_at >= month_start, 1),
                )
            ).label("this_month"),
            func.avg(
                case((Invoice.invoice_type == "revenue", Invoice.amount))
            ).label("avg_value"),
            func.count(
                case(
                    (
                        (Invoice.invoice_type == "revenue") & (Invoice.status == "paid"),
                        1,
                    )
                )
            ).label("paid_revenue"),
            func.count(
                case(
                    (Invoice.invoice_type == "revenue", 1),
                )
            ).label("total_revenue_count"),
        )
        .group_by(Invoice.issuer_id)
        .all()
    )
    inv_map: dict[int, Any] = {row.issuer_id: row for row in inv_stats}

    # Pre-fetch customer count per user
    cust_stats = (
        db.query(
            Invoice.issuer_id,
            func.count(func.distinct(Invoice.customer_id)).label("cust_count"),
        )
        .filter(Invoice.customer_id.isnot(None))
        .group_by(Invoice.issuer_id)
        .all()
    )
    cust_map: dict[int, int] = {row.issuer_id: row.cust_count for row in cust_stats}

    # ── Build business items ──
    items: list[BusinessHealthItem] = []

    for u in all_users:
        inv = inv_map.get(u.id)
        total_rev = float(inv.revenue or 0) if inv else 0
        total_exp = float(inv.expenses or 0) if inv else 0
        inv_total = inv.total if inv else 0
        inv_paid = inv.paid if inv else 0
        inv_pending = inv.pending if inv else 0
        inv_this_month = inv.this_month if inv else 0
        avg_val = round(float(inv.avg_value or 0), 2) if inv else 0
        paid_rev = inv.paid_revenue if inv else 0
        total_rev_count = inv.total_revenue_count if inv else 0
        last_inv = inv.last_invoice if inv else None
        customers = cust_map.get(u.id, 0)

        collection = (
            round(paid_rev / total_rev_count * 100, 1) if total_rev_count > 0 else 0
        )

        # Subscription status
        sub_status = "free"
        days_until = None
        if u.plan == SubscriptionPlan.PRO:
            if u.subscription_expires_at:
                if u.subscription_expires_at < now:
                    sub_status = "expired"
                elif u.subscription_expires_at <= now + dt.timedelta(days=7):
                    sub_status = "expiring_soon"
                    days_until = (u.subscription_expires_at - now).days
                else:
                    sub_status = "active"
                    days_until = (u.subscription_expires_at - now).days
            else:
                sub_status = "active"

        # Days since last invoice
        days_since = None
        if last_inv:
            if hasattr(last_inv, "tzinfo") and last_inv.tzinfo is None:
                last_inv = last_inv.replace(tzinfo=dt.timezone.utc)
            days_since = (now - last_inv).days

        # ── Health Score (0–100) ──
        score = 50  # baseline

        # Activity (+/- 30)
        if days_since is not None:
            if days_since <= 3:
                score += 30
            elif days_since <= 7:
                score += 20
            elif days_since <= 14:
                score += 10
            elif days_since <= 30:
                score += 0
            elif days_since <= 60:
                score -= 10
            else:
                score -= 20
        else:
            # never created an invoice
            score -= 25

        # Collection rate (+/- 15)
        if total_rev_count >= 3:
            if collection >= 70:
                score += 15
            elif collection >= 40:
                score += 5
            else:
                score -= 10

        # Invoice volume (+/- 10)
        if inv_this_month >= 10:
            score += 10
        elif inv_this_month >= 3:
            score += 5
        elif inv_total == 0:
            score -= 5

        # Paid plan bonus
        if u.plan == SubscriptionPlan.PRO:
            score += 10

        # Subscription expired penalty
        if sub_status == "expired":
            score -= 15

        score = max(0, min(100, score))

        # Risk flags
        flags: list[str] = []
        if inv_total == 0:
            flags.append("never_invoiced")
        if days_since is not None and days_since > 30:
            flags.append("inactive_30d")
        if days_since is not None and days_since > 60:
            flags.append("inactive_60d")
        if sub_status == "expired":
            flags.append("subscription_expired")
        if sub_status == "expiring_soon":
            flags.append("subscription_expiring")
        if total_rev_count >= 5 and collection < 30:
            flags.append("low_collection")
        if u.plan == SubscriptionPlan.FREE and inv_total >= 3 and u.invoice_balance <= 1:
            flags.append("upgrade_candidate")
        if inv_this_month >= 10:
            flags.append("power_user")

        item = BusinessHealthItem(
            id=u.id,
            name=u.name,
            business_name=u.business_name,
            phone=u.phone,
            email=u.email,
            plan=u.plan.value,
            created_at=u.created_at.isoformat(),
            last_login=u.last_login.isoformat() if u.last_login else None,
            subscription_started_at=u.subscription_started_at.isoformat() if u.subscription_started_at else None,
            subscription_expires_at=u.subscription_expires_at.isoformat() if u.subscription_expires_at else None,
            subscription_status=sub_status,
            days_until_expiry=days_until,
            invoice_balance=u.invoice_balance,
            total_revenue=total_rev,
            total_expenses=total_exp,
            net_income=round(total_rev - total_exp, 2),
            invoices_total=inv_total,
            invoices_paid=inv_paid,
            invoices_pending=inv_pending,
            collection_rate=collection,
            customers_count=customers,
            invoices_this_month=inv_this_month,
            last_invoice_date=last_inv.isoformat() if last_inv else None,
            days_since_last_invoice=days_since,
            avg_invoice_value=avg_val,
            health_score=score,
            risk_flags=flags,
        )

        items.append(item)

    # ── Risk filter ──
    if risk_filter == "at_risk":
        items = [i for i in items if i.health_score < 40]
    elif risk_filter == "healthy":
        items = [i for i in items if i.health_score >= 60]
    elif risk_filter == "inactive":
        items = [i for i in items if "inactive_30d" in i.risk_flags or "never_invoiced" in i.risk_flags]
    elif risk_filter == "churned":
        items = [i for i in items if "subscription_expired" in i.risk_flags]

    # ── Sort ──
    reverse = sort_order == "desc"
    key_map = {
        "health_score": lambda x: x.health_score,
        "total_revenue": lambda x: x.total_revenue,
        "invoices_total": lambda x: x.invoices_total,
        "created_at": lambda x: x.created_at,
        "last_login": lambda x: x.last_login or "",
        "name": lambda x: x.name.lower(),
        "collection_rate": lambda x: x.collection_rate,
    }
    items.sort(key=key_map[sort_by], reverse=reverse)

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return BusinessListResponse(
        businesses=page_items,
        total=total,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# USER SEGMENTS FOR CAMPAIGNS (Brevo Email/WhatsApp Export)
# =============================================================================

class UserSegmentExport(BaseModel):
    """User data formatted for Brevo campaign import."""
    name: str
    phone: str | None
    email: str | None
    plan: str
    invoice_balance: int
    total_invoices: int
    days_since_signup: int
    days_since_last_login: int | None
    business_name: str | None


@router.get("/users/segments/inactive", response_model=list[UserSegmentExport])
def get_inactive_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    days_inactive: int = Query(7, description="Days since last login to consider inactive"),
) -> list[UserSegmentExport]:
    """
    Get users who registered but never created an invoice.
    Perfect for activation campaign.
    
    Export this list to Brevo for Email/WhatsApp campaign targeting.
    """
    log_audit_event("admin.segments.inactive", user_id=admin_user.id, days=days_inactive)
    
    now = dt.datetime.now(dt.timezone.utc)
    
    # Users with 0 invoices
    users_with_invoices = db.query(models.Invoice.issuer_id).distinct().subquery()
    
    inactive_users = db.query(models.User).filter(
        ~models.User.id.in_(db.query(users_with_invoices))
    ).all()
    
    result = []
    for user in inactive_users:
        days_since_signup = (now - user.created_at.replace(tzinfo=dt.timezone.utc)).days if user.created_at else 0
        days_since_login = None
        if user.last_login:
            days_since_login = (now - user.last_login.replace(tzinfo=dt.timezone.utc)).days
        
        result.append(UserSegmentExport(
            name=user.name or "Customer",
            phone=user.phone,
            email=user.email,
            plan=user.plan.value,
            invoice_balance=getattr(user, 'invoice_balance', 5),
            total_invoices=0,
            days_since_signup=days_since_signup,
            days_since_last_login=days_since_login,
            business_name=user.business_name
        ))
    
    return result


@router.get("/users/segments/low-balance", response_model=list[UserSegmentExport])
def get_low_balance_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    max_balance: int = Query(2, description="Maximum invoice balance to include"),
) -> list[UserSegmentExport]:
    """
    Get FREE users with low invoice balance (1-2 left).
    Perfect for upgrade campaign - "Running low! Buy 100 for ₦2,500"
    """
    log_audit_event("admin.segments.low_balance", user_id=admin_user.id, max_balance=max_balance)
    
    now = dt.datetime.now(dt.timezone.utc)
    
    low_balance_users = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.FREE,
        models.User.invoice_balance <= max_balance,
        models.User.invoice_balance > 0  # Still have some
    ).all()
    
    result = []
    for user in low_balance_users:
        # Count their invoices
        invoice_count = db.query(func.count(models.Invoice.id)).filter(
            models.Invoice.issuer_id == user.id
        ).scalar() or 0
        
        days_since_signup = (now - user.created_at.replace(tzinfo=dt.timezone.utc)).days if user.created_at else 0
        days_since_login = None
        if user.last_login:
            days_since_login = (now - user.last_login.replace(tzinfo=dt.timezone.utc)).days
        
        result.append(UserSegmentExport(
            name=user.name or "Customer",
            phone=user.phone,
            email=user.email,
            plan=user.plan.value,
            invoice_balance=user.invoice_balance,
            total_invoices=invoice_count,
            days_since_signup=days_since_signup,
            days_since_last_login=days_since_login,
            business_name=user.business_name
        ))
    
    return result


@router.get("/users/segments/active-free", response_model=list[UserSegmentExport])
def get_active_free_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    min_invoices: int = Query(3, description="Minimum invoices created"),
) -> list[UserSegmentExport]:
    """
    Get active FREE users who create invoices but haven't upgraded.
    Perfect for upgrade campaign - "You're invoicing a lot! Upgrade to Pro"
    """
    log_audit_event("admin.segments.active_free", user_id=admin_user.id, min_invoices=min_invoices)
    
    now = dt.datetime.now(dt.timezone.utc)
    
    # Get users with invoice counts
    user_invoice_counts = db.query(
        models.Invoice.issuer_id,
        func.count(models.Invoice.id).label('invoice_count')
    ).group_by(models.Invoice.issuer_id).having(
        func.count(models.Invoice.id) >= min_invoices
    ).subquery()
    
    active_free_users = db.query(models.User, user_invoice_counts.c.invoice_count).join(
        user_invoice_counts,
        models.User.id == user_invoice_counts.c.issuer_id
    ).filter(
        models.User.plan == SubscriptionPlan.FREE
    ).all()
    
    result = []
    for user, invoice_count in active_free_users:
        days_since_signup = (now - user.created_at.replace(tzinfo=dt.timezone.utc)).days if user.created_at else 0
        days_since_login = None
        if user.last_login:
            days_since_login = (now - user.last_login.replace(tzinfo=dt.timezone.utc)).days
        
        result.append(UserSegmentExport(
            name=user.name or "Customer",
            phone=user.phone,
            email=user.email,
            plan=user.plan.value,
            invoice_balance=getattr(user, 'invoice_balance', 5),
            total_invoices=invoice_count,
            days_since_signup=days_since_signup,
            days_since_last_login=days_since_login,
            business_name=user.business_name
        ))
    
    return result


@router.get("/users/segments/churned", response_model=list[UserSegmentExport])
def get_churned_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    days_inactive: int = Query(14, description="Days since last login"),
) -> list[UserSegmentExport]:
    """
    Get users who haven't logged in for X days but had activity before.
    Perfect for win-back campaign - "We miss you! Create an invoice today"
    """
    log_audit_event("admin.segments.churned", user_id=admin_user.id, days=days_inactive)
    
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=days_inactive)
    
    # Users who have invoices but haven't logged in recently
    users_with_invoices = db.query(models.Invoice.issuer_id).distinct().subquery()
    
    churned_users = db.query(models.User).filter(
        models.User.id.in_(db.query(users_with_invoices)),
        models.User.last_login < cutoff
    ).all()
    
    result = []
    for user in churned_users:
        invoice_count = db.query(func.count(models.Invoice.id)).filter(
            models.Invoice.issuer_id == user.id
        ).scalar() or 0
        
        days_since_signup = (now - user.created_at.replace(tzinfo=dt.timezone.utc)).days if user.created_at else 0
        days_since_login = (now - user.last_login.replace(tzinfo=dt.timezone.utc)).days if user.last_login else None
        
        result.append(UserSegmentExport(
            name=user.name or "Customer",
            phone=user.phone,
            email=user.email,
            plan=user.plan.value,
            invoice_balance=getattr(user, 'invoice_balance', 5),
            total_invoices=invoice_count,
            days_since_signup=days_since_signup,
            days_since_last_login=days_since_login,
            business_name=user.business_name
        ))
    
    return result


@router.get("/users/segments/starter", response_model=list[UserSegmentExport])
def get_starter_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> list[UserSegmentExport]:
    """
    Get FREE plan users who have bought invoice packs (legacy "starter" users).
    Perfect for Pro upsell campaign - "Unlock analytics, inventory, team management"
    Note: STARTER plan removed — returns FREE users with invoice packs purchased.
    """
    log_audit_event("admin.segments.starter", user_id=admin_user.id)
    
    now = dt.datetime.now(dt.timezone.utc)
    
    # Return FREE users who have purchased packs (invoice_balance > 2 or have transactions)
    starter_users = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.FREE,
        models.User.invoice_balance > 2,  # More than the initial 2 free invoices
    ).all()
    
    result = []
    for user in starter_users:
        invoice_count = db.query(func.count(models.Invoice.id)).filter(
            models.Invoice.issuer_id == user.id
        ).scalar() or 0
        
        days_since_signup = (now - user.created_at.replace(tzinfo=dt.timezone.utc)).days if user.created_at else 0
        days_since_login = None
        if user.last_login:
            days_since_login = (now - user.last_login.replace(tzinfo=dt.timezone.utc)).days
        
        result.append(UserSegmentExport(
            name=user.name or "Customer",
            phone=user.phone,
            email=user.email,
            plan=user.plan.value,
            invoice_balance=getattr(user, 'invoice_balance', 100),
            total_invoices=invoice_count,
            days_since_signup=days_since_signup,
            days_since_last_login=days_since_login,
            business_name=user.business_name
        ))
    
    return result


@router.get("/users/segments/pro", response_model=list[UserSegmentExport])
def get_pro_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> list[UserSegmentExport]:
    """
    Get PRO plan users (monthly subscribers).
    Perfect for retention/engagement campaign - "Tips to get more value"
    """
    log_audit_event("admin.segments.pro", user_id=admin_user.id)
    
    now = dt.datetime.now(dt.timezone.utc)
    
    pro_users = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.PRO
    ).all()
    
    result = []
    for user in pro_users:
        invoice_count = db.query(func.count(models.Invoice.id)).filter(
            models.Invoice.issuer_id == user.id
        ).scalar() or 0
        
        days_since_signup = (now - user.created_at.replace(tzinfo=dt.timezone.utc)).days if user.created_at else 0
        days_since_login = None
        if user.last_login:
            days_since_login = (now - user.last_login.replace(tzinfo=dt.timezone.utc)).days
        
        result.append(UserSegmentExport(
            name=user.name or "Customer",
            phone=user.phone,
            email=user.email,
            plan=user.plan.value,
            invoice_balance=getattr(user, 'invoice_balance', 100),
            total_invoices=invoice_count,
            days_since_signup=days_since_signup,
            days_since_last_login=days_since_login,
            business_name=user.business_name
        ))
    
    return result


# =============================================================================
# BREVO SYNC - Push segments directly to Brevo lists
# =============================================================================

class BrevoSyncResult(BaseModel):
    """Result of syncing a segment to Brevo."""
    segment: str
    contacts_synced: int
    list_id: int
    success: bool
    error: str | None = None


@router.post("/brevo/sync/{segment}", response_model=BrevoSyncResult)
async def sync_segment_to_brevo(
    segment: str,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    list_id: int = Query(..., description="Brevo list ID to sync contacts to"),
) -> BrevoSyncResult:
    """
    Sync a user segment directly to a Brevo contact list.
    
    Segments: inactive, low-balance, active-free, churned, starter, pro, all
    
    1. First create lists in Brevo Dashboard → Contacts → Lists
    2. Get the list ID from Brevo
    3. Call this endpoint to push contacts to that list
    """
    import httpx

    from app.core.config import settings
    
    log_audit_event("admin.brevo.sync", user_id=admin_user.id, segment=segment, list_id=list_id)
    
    brevo_api_key = getattr(settings, "BREVO_CONTACTS_API_KEY", None)
    if not brevo_api_key:
        return BrevoSyncResult(
            segment=segment,
            contacts_synced=0,
            list_id=list_id,
            success=False,
            error="BREVO_CONTACTS_API_KEY not configured"
        )
    
    # Get users based on segment (column-only queries to save RAM at scale)
    now = dt.datetime.now(dt.timezone.utc)
    _brevo_cols = (
        models.User.email, models.User.name, models.User.phone,
        models.User.plan, models.User.invoice_balance, models.User.business_name,
    )
    users = []
    
    if segment == "inactive":
        # Users who never created an invoice
        users_with_invoices = db.query(models.Invoice.issuer_id).distinct()
        users = db.query(*_brevo_cols).filter(
            ~models.User.id.in_(users_with_invoices)
        ).all()
    
    elif segment == "low-balance":
        # FREE users with low invoice balance
        users = db.query(*_brevo_cols).filter(
            models.User.plan == SubscriptionPlan.FREE,
            models.User.invoice_balance <= 2,
            models.User.invoice_balance > 0
        ).all()
    
    elif segment == "active-free":
        # Active FREE users with 3+ invoices
        user_invoice_counts = db.query(
            models.Invoice.issuer_id,
            func.count(models.Invoice.id).label('invoice_count')
        ).group_by(models.Invoice.issuer_id).having(
            func.count(models.Invoice.id) >= 3
        ).subquery()
        
        users = db.query(*_brevo_cols).filter(
            models.User.id.in_(
                db.query(user_invoice_counts.c.issuer_id)
            ),
            models.User.plan == SubscriptionPlan.FREE
        ).all()
    
    elif segment == "churned":
        # Users inactive for 14+ days
        cutoff = now - dt.timedelta(days=14)
        users_with_invoices = db.query(models.Invoice.issuer_id).distinct()
        users = db.query(*_brevo_cols).filter(
            models.User.id.in_(users_with_invoices),
            models.User.last_login < cutoff
        ).all()
    
    elif segment == "starter":
        # Legacy: FREE users who bought packs (invoice_balance > 5) - for Pro upsell
        users = db.query(*_brevo_cols).filter(
            models.User.plan == SubscriptionPlan.FREE,
            models.User.invoice_balance > 5,
        ).all()
    
    elif segment == "pro":
        # PRO plan users (monthly subscribers) - for retention
        users = db.query(*_brevo_cols).filter(
            models.User.plan == SubscriptionPlan.PRO
        ).all()
    
    elif segment == "all":
        # ALL users - sync entire user base to Brevo
        users = db.query(*_brevo_cols).all()
    
    else:
        return BrevoSyncResult(
            segment=segment,
            contacts_synced=0,
            list_id=list_id,
            success=False,
            error=f"Unknown segment: {segment}. Valid: inactive, low-balance, active-free, churned, starter, pro, all"
        )
    
    if not users:
        return BrevoSyncResult(
            segment=segment,
            contacts_synced=0,
            list_id=list_id,
            success=True,
            error=None
        )
    
    # Prepare contacts for Brevo
    contacts = []
    for user in users:
        if user.email:  # Brevo requires email
            contact = {
                "email": user.email,
                "attributes": {
                    "FIRSTNAME": user.name or "Customer",
                    "PHONE": user.phone,
                    "PLAN": user.plan.value,
                    "INVOICE_BALANCE": getattr(user, 'invoice_balance', 5),
                    "BUSINESS_NAME": user.business_name or ""
                },
                "listIds": [list_id],
                "updateEnabled": True  # Update if contact exists
            }
            contacts.append(contact)
    
    if not contacts:
        return BrevoSyncResult(
            segment=segment,
            contacts_synced=0,
            list_id=list_id,
            success=True,
            error="No users with email addresses in this segment"
        )
    
    # Push to Brevo using batch import
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.brevo.com/v3/contacts/import",
                headers={
                    "api-key": brevo_api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "listIds": [list_id],
                    "updateExistingContacts": True,
                    "jsonBody": contacts
                },
                timeout=30.0
            )
            
            if response.status_code in (200, 201, 202):
                return BrevoSyncResult(
                    segment=segment,
                    contacts_synced=len(contacts),
                    list_id=list_id,
                    success=True,
                    error=None
                )
            else:
                return BrevoSyncResult(
                    segment=segment,
                    contacts_synced=0,
                    list_id=list_id,
                    success=False,
                    error=f"Brevo API error: {response.status_code} - {response.text}"
                )
    
    except Exception as e:
        return BrevoSyncResult(
            segment=segment,
            contacts_synced=0,
            list_id=list_id,
            success=False,
            error=str(e)
        )


@router.get("/brevo/lists")
async def get_brevo_lists(
    admin_user=Depends(get_current_admin),
) -> dict:
    """
    Get all Brevo contact lists to find list IDs for syncing.
    """
    import httpx

    from app.core.config import settings
    
    brevo_api_key = getattr(settings, "BREVO_CONTACTS_API_KEY", None)
    if not brevo_api_key:
        return {"error": "BREVO_CONTACTS_API_KEY not configured", "lists": []}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.brevo.com/v3/contacts/lists",
                headers={"api-key": brevo_api_key},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "lists": [
                        {"id": lst["id"], "name": lst["name"], "totalSubscribers": lst.get("totalSubscribers", 0)}
                        for lst in data.get("lists", [])
                    ]
                }
            else:
                return {"error": f"Brevo API error: {response.status_code}", "lists": []}
    
    except Exception as e:
        return {"error": str(e), "lists": []}


@router.post("/brevo/create-list")
async def create_brevo_list(
    name: str = Query(..., description="Name for the new list"),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Create a new contact list in Brevo."""
    import httpx

    from app.core.config import settings
    
    brevo_api_key = getattr(settings, "BREVO_CONTACTS_API_KEY", None)
    if not brevo_api_key:
        return {"error": "BREVO_CONTACTS_API_KEY not configured", "list_id": None}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.brevo.com/v3/contacts/lists",
                headers={
                    "api-key": brevo_api_key,
                    "Content-Type": "application/json"
                },
                json={"name": name, "folderId": 1},  # folderId 1 is usually the default folder
                timeout=10.0
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                return {"list_id": data.get("id"), "name": name, "success": True}
            else:
                return {"error": f"Brevo API error: {response.status_code} - {response.text}", "list_id": None}
    
    except Exception as e:
        return {"error": str(e), "list_id": None}


@router.get("/users/export/csv")
def export_users_csv(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
):
    """
    Export all users as CSV for Brevo import.
    
    Download this file and upload to Brevo:
    Contacts → Import contacts → Upload file
    """
    import io

    from fastapi.responses import StreamingResponse
    
    users = db.query(
        models.User.email, models.User.name, models.User.phone,
        models.User.plan, models.User.invoice_balance, models.User.business_name,
    ).all()
    
    # Build CSV
    output = io.StringIO()
    output.write("EMAIL,FIRSTNAME,PHONE,PLAN,INVOICE_BALANCE,BUSINESS_NAME\n")
    
    for user in users:
        if user.email:  # Brevo requires email
            row = [
                user.email,
                (user.name or "Customer").replace(",", " "),
                user.phone or "",
                user.plan.value,
                str(getattr(user, 'invoice_balance', 5)),
                (user.business_name or "").replace(",", " ")
            ]
            output.write(",".join(row) + "\n")
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=suoops_users.csv"}
    )


# ============================================================================
# Celery Task Management
# ============================================================================

ALLOWED_TASKS = {
    "engagement": "engagement.send_lifecycle_emails",
    "daily_summary": "summary.send_daily_summaries",
    "overdue_reminders": "maintenance.send_overdue_reminders",
    "customer_reminders": "reminders.send_customer_payment_reminders",
    "mark_paid_nudges": "reminders.send_mark_paid_nudges",
    "tax_reports": "tax.generate_previous_month_reports",
    "morning_insights": "insights.send_morning_insights",
    "dormant_nudges": "customer_engagement.send_dormant_customer_nudges",
    "referral_asks": "customer_engagement.send_post_payment_referrals",
    "warn_inactive": "maintenance.warn_inactive_accounts",
    "delete_inactive": "maintenance.delete_inactive_accounts",
    "activation_nudges": "maintenance.nudge_zero_invoice_users",
    "reconcile_brevo": "maintenance.reconcile_brevo_contacts",
    "reconcile_brevo_dry": "maintenance.reconcile_brevo_contacts",
    "feature_announcement": "announcement.send_feature_announcement",
}


@router.post("/purge-inactive-accounts")
def purge_inactive_accounts(
    days: int = 60,
    channel: str = "all",
    max_invoices: int = 0,
    admin_user=Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Immediately delete inactive accounts older than N days.

    No warning — direct deletion. Only deletes FREE users.

    Parameters:
    - days: Minimum inactive days (default 60)
    - channel: "all", "email_only" (no WhatsApp), or "whatsapp" (phone verified)
    - max_invoices: Maximum invoice count to qualify for deletion (default 0 = zero invoices only)
    """
    import datetime as _dt

    from sqlalchemy import func as sqlfunc

    from app.models.models import Invoice, SubscriptionPlan, User
    from app.services.account_deletion_service import AccountDeletionService

    log_audit_event("admin.purge_inactive", user_id=admin_user.id, days=days, channel=channel, max_invoices=max_invoices)

    if days < 14:
        raise HTTPException(status_code=400, detail="Minimum 14 days threshold for safety")

    now = _dt.datetime.now(_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=days)

    # Count invoices per user
    invoice_counts = (
        db.query(Invoice.issuer_id, sqlfunc.count(Invoice.id).label("cnt"))
        .group_by(Invoice.issuer_id)
        .subquery()
    )

    # Find inactive free users with invoices <= max_invoices
    query = (
        db.query(User)
        .outerjoin(invoice_counts, User.id == invoice_counts.c.issuer_id)
        .filter(
            User.plan == SubscriptionPlan.FREE,
            (
                (invoice_counts.c.cnt == None)  # noqa: E711 — zero invoices
                | (invoice_counts.c.cnt <= max_invoices)
            ),
            (
                ((User.last_login != None) & (User.last_login < cutoff))  # noqa: E711
                | ((User.last_login == None) & (User.created_at < cutoff))  # noqa: E711
            ),
        )
    )

    # Channel filter
    if channel == "email_only":
        query = query.filter(
            (User.phone_verified.is_(False)) | (User.phone == None)  # noqa: E711
        )
    elif channel == "whatsapp":
        query = query.filter(
            User.phone_verified.is_(True),
            User.phone != None,  # noqa: E711
        )

    inactive = query.all()

    if not inactive:
        return {"deleted": 0, "message": "No inactive empty accounts found"}

    service = AccountDeletionService(db)
    deleted = 0
    failed = 0
    deleted_ids = []

    for user in inactive:
        try:
            uid = user.id
            service.delete_account(user_id=uid, deleted_by_user_id=None)
            deleted += 1
            deleted_ids.append(uid)
        except Exception as e:
            failed += 1
            logger.warning("Failed to purge user %s: %s", user.id, e)

    logger.info(
        "Admin %s purged %d inactive accounts (days=%d, failed=%d)",
        admin_user.id, deleted, days, failed,
    )

    return {
        "deleted": deleted,
        "failed": failed,
        "days_threshold": days,
        "channel": channel,
        "deleted_user_ids": deleted_ids[:50],
        "message": f"Deleted {deleted} inactive empty accounts (inactive {days}+ days, channel={channel})",
    }


@router.post("/purge-low-quality-accounts")
def purge_low_quality_accounts(
    dry_run: bool = True,
    admin_user=Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Purge accounts without a business name and fewer than 5 invoices.

    Protects:
    - PRO subscribers
    - Users who purchased invoice packs (any successful payment)

    Parameters:
    - dry_run: If True (default), only count — don't delete. Set to False to actually purge.
    """
    from sqlalchemy import func as sqlfunc

    from app.models.models import Invoice, SubscriptionPlan, User
    from app.models.payment_models import PaymentStatus, PaymentTransaction

    log_audit_event("admin.purge_low_quality", user_id=admin_user.id, dry_run=dry_run)

    invoice_counts = (
        db.query(Invoice.issuer_id, sqlfunc.count(Invoice.id).label("cnt"))
        .group_by(Invoice.issuer_id)
        .subquery()
    )

    # Users who have made any successful payment (subscription or invoice pack)
    paying_user_ids = (
        db.query(PaymentTransaction.user_id)
        .filter(PaymentTransaction.status == PaymentStatus.SUCCESS)
        .distinct()
        .subquery()
    )

    candidates = (
        db.query(User)
        .outerjoin(invoice_counts, User.id == invoice_counts.c.issuer_id)
        .filter(
            User.plan != SubscriptionPlan.PRO,
            ~User.id.in_(db.query(paying_user_ids)),
            (User.business_name.is_(None)) | (User.business_name == ""),
            (invoice_counts.c.cnt.is_(None)) | (invoice_counts.c.cnt < 5),
        )
        .all()
    )

    if dry_run:
        zero = sum(1 for _ in candidates if not hasattr(_, "_cnt"))
        return {
            "dry_run": True,
            "would_delete": len(candidates),
            "message": f"Would delete {len(candidates)} accounts (no business name + <5 invoices). Set dry_run=false to execute.",
        }

    if not candidates:
        return {"deleted": 0, "message": "No low-quality accounts found"}

    from app.services.account_deletion_service import AccountDeletionService
    service = AccountDeletionService(db)
    deleted = 0
    failed = 0
    deleted_ids = []

    for user in candidates:
        try:
            uid = user.id
            service.delete_account(user_id=uid, deleted_by_user_id=None)
            deleted += 1
            deleted_ids.append(uid)
        except Exception as e:
            failed += 1
            logger.warning("Failed to purge low-quality user %s: %s", user.id, e)

    logger.info(
        "Admin %s purged %d low-quality accounts (failed=%d)",
        admin_user.id, deleted, failed,
    )

    return {
        "deleted": deleted,
        "failed": failed,
        "deleted_user_ids": deleted_ids[:50],
        "message": f"Deleted {deleted} low-quality accounts (no business name + <5 invoices)",
    }


@router.post("/purge-no-bank-accounts")
def purge_no_bank_accounts(
    dry_run: bool = True,
    admin_user=Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Purge accounts without bank details and fewer than 5 invoices.

    Protects:
    - PRO subscribers
    - Users who purchased invoice packs (any successful payment)

    Parameters:
    - dry_run: If True (default), only count. Set to False to actually purge.
    """
    from sqlalchemy import func as sqlfunc

    from app.models.models import Invoice, SubscriptionPlan, User
    from app.models.payment_models import PaymentStatus, PaymentTransaction

    log_audit_event("admin.purge_no_bank", user_id=admin_user.id, dry_run=dry_run)

    invoice_counts = (
        db.query(Invoice.issuer_id, sqlfunc.count(Invoice.id).label("cnt"))
        .group_by(Invoice.issuer_id)
        .subquery()
    )

    paying_user_ids = (
        db.query(PaymentTransaction.user_id)
        .filter(PaymentTransaction.status == PaymentStatus.SUCCESS)
        .distinct()
        .subquery()
    )

    candidates = (
        db.query(User)
        .outerjoin(invoice_counts, User.id == invoice_counts.c.issuer_id)
        .filter(
            User.plan != SubscriptionPlan.PRO,
            ~User.id.in_(db.query(paying_user_ids)),
            (User.bank_name.is_(None)) | (User.bank_name == ""),
            (User.account_number.is_(None)) | (User.account_number == ""),
            (invoice_counts.c.cnt.is_(None)) | (invoice_counts.c.cnt < 5),
        )
        .all()
    )

    if dry_run:
        return {
            "dry_run": True,
            "would_delete": len(candidates),
            "message": f"Would delete {len(candidates)} accounts (no bank details + <5 invoices). Set dry_run=false to execute.",
        }

    if not candidates:
        return {"deleted": 0, "message": "No accounts without bank details found"}

    from app.services.account_deletion_service import AccountDeletionService
    service = AccountDeletionService(db)
    deleted = 0
    failed = 0
    deleted_ids = []

    for user in candidates:
        try:
            uid = user.id
            service.delete_account(user_id=uid, deleted_by_user_id=None)
            deleted += 1
            deleted_ids.append(uid)
        except Exception as e:
            failed += 1
            logger.warning("Failed to purge no-bank user %s: %s", user.id, e)

    logger.info(
        "Admin %s purged %d no-bank accounts (failed=%d)",
        admin_user.id, deleted, failed,
    )

    return {
        "deleted": deleted,
        "failed": failed,
        "deleted_user_ids": deleted_ids[:50],
        "message": f"Deleted {deleted} accounts (no bank details + <5 invoices)",
    }


@router.post("/sync-brevo-contacts")
def sync_brevo_contacts(
    admin_user=Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Sync Brevo contacts with current database.

    Fetches all contacts from Brevo, cross-references with DB,
    and deletes contacts whose emails no longer exist in the DB.
    Also re-syncs all current users to ensure lists are accurate.
    """
    import httpx

    from app.core.config import settings as _settings

    log_audit_event("admin.sync_brevo", user_id=admin_user.id)

    brevo_api_key = getattr(_settings, "BREVO_CONTACTS_API_KEY", None)
    if not brevo_api_key:
        raise HTTPException(status_code=400, detail="BREVO_CONTACTS_API_KEY not configured")

    # Get all current user emails from DB (column-only query, no full objects)
    db_emails = set()
    for row in db.query(models.User.email).filter(models.User.email != None).all():  # noqa: E711
        if row.email:
            db_emails.add(row.email.lower())

    # Fetch all contacts from Brevo (paginated)
    headers = {"api-key": brevo_api_key, "Content-Type": "application/json"}
    brevo_contacts = []
    offset = 0
    limit = 50

    with httpx.Client(timeout=15.0) as client:
        while True:
            resp = client.get(
                f"https://api.brevo.com/v3/contacts?limit={limit}&offset={offset}",
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning("Brevo fetch contacts failed: %s", resp.status_code)
                break
            data = resp.json()
            contacts = data.get("contacts", [])
            if not contacts:
                break
            brevo_contacts.extend(contacts)
            offset += limit
            if offset >= data.get("count", 0):
                break

    # Find contacts in Brevo that aren't in the DB
    orphaned = []
    for contact in brevo_contacts:
        email = contact.get("email", "").lower()
        if email and email not in db_emails:
            orphaned.append(email)

    # Delete orphaned contacts from Brevo
    deleted = 0
    with httpx.Client(timeout=10.0) as client:
        for email in orphaned:
            try:
                encoded = email.replace("@", "%40")
                resp = client.delete(
                    f"https://api.brevo.com/v3/contacts/{encoded}",
                    headers=headers,
                )
                if resp.status_code in (200, 204, 404):
                    deleted += 1
                else:
                    logger.warning("Brevo delete %s: %s", email, resp.status_code)
            except Exception as e:
                logger.warning("Brevo delete error %s: %s", email, e)

    logger.info(
        "Admin %s synced Brevo: %d total contacts, %d orphaned, %d deleted",
        admin_user.id, len(brevo_contacts), len(orphaned), deleted,
    )

    return {
        "total_brevo_contacts": len(brevo_contacts),
        "current_db_users": len(db_emails),
        "orphaned_contacts": len(orphaned),
        "deleted_from_brevo": deleted,
        "message": f"Removed {deleted} orphaned contacts from Brevo",
    }


@router.get("/tasks/schedule")
def get_task_schedule(
    admin_user=Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Show all scheduled Celery Beat tasks, recent email log counts, and worker connectivity."""
    from app.workers.celery_app import celery_app as celery

    # Beat schedule
    schedule_info = []
    beat_schedule = getattr(celery.conf, "beat_schedule", {}) or {}
    for name, entry in beat_schedule.items():
        sched = entry.get("schedule")
        schedule_info.append({
            "name": name,
            "task": entry.get("task"),
            "schedule": str(sched) if sched else "unknown",
        })

    # Recent engagement email stats (last 24h and last 7d)
    from app.models.models import UserEmailLog

    now = dt.datetime.now(dt.timezone.utc)
    day_ago = now - dt.timedelta(hours=24)
    week_ago = now - dt.timedelta(days=7)

    emails_24h = db.query(func.count(UserEmailLog.id)).filter(
        UserEmailLog.sent_at >= day_ago
    ).scalar() or 0

    emails_7d = db.query(func.count(UserEmailLog.id)).filter(
        UserEmailLog.sent_at >= week_ago
    ).scalar() or 0

    # Breakdown by type (last 7d)
    type_counts = (
        db.query(UserEmailLog.email_type, func.count(UserEmailLog.id))
        .filter(UserEmailLog.sent_at >= week_ago)
        .group_by(UserEmailLog.email_type)
        .all()
    )

    # Check worker connectivity
    worker_status = "unknown"
    try:
        inspect = celery.control.inspect(timeout=3)
        active = inspect.active()
        worker_status = "connected" if active else "no_workers"
    except Exception:
        worker_status = "unreachable"

    return {
        "schedule": schedule_info,
        "worker_status": worker_status,
        "email_stats": {
            "sent_last_24h": emails_24h,
            "sent_last_7d": emails_7d,
            "by_type_7d": {t: c for t, c in type_counts},
        },
    }


@router.post("/tasks/{task_key}/trigger")
def trigger_task(
    task_key: str,
    admin_user=Depends(get_current_admin),
) -> dict:
    """Manually trigger a scheduled Celery task for testing."""
    if task_key not in ALLOWED_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task '{task_key}'. Allowed: {list(ALLOWED_TASKS.keys())}",
        )

    from app.workers.celery_app import celery_app as celery

    task_name = ALLOWED_TASKS[task_key]
    args = ["paid"] if task_key == "tax_reports" else []
    kwargs = {"dry_run": True} if task_key == "reconcile_brevo_dry" else {}

    result = celery.send_task(task_name, args=args, kwargs=kwargs)

    log_audit_event(
        "admin.tasks.trigger",
        user_id=admin_user.id,
        task_key=task_key,
        task_name=task_name,
        celery_task_id=result.id,
    )
    logger.info("Admin %s triggered task %s (celery_id=%s)", admin_user.id, task_name, result.id)

    return {
        "triggered": True,
        "task_key": task_key,
        "task_name": task_name,
        "celery_task_id": result.id,
        "message": f"Task '{task_key}' dispatched to worker. Check Render worker logs for output.",
    }


# ============================================================================
# Testimonial Management
# ============================================================================


class AdminTestimonialItem(BaseModel):
    id: int
    user_id: int
    user_name: str
    business_name: str | None
    email: str | None
    text: str
    rating: int
    approved: bool
    featured: bool
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("/testimonials", response_model=list[AdminTestimonialItem])
def list_testimonials(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    status: str = Query("all", description="Filter: all, pending, approved"),
) -> Any:
    """List all testimonials for admin review."""
    from app.models.models import Testimonial

    log_audit_event("admin.testimonials.list", user_id=admin_user.id)

    query = db.query(Testimonial).join(models.User, Testimonial.user_id == models.User.id)

    if status == "pending":
        query = query.filter(Testimonial.approved.is_(False))
    elif status == "approved":
        query = query.filter(Testimonial.approved.is_(True))

    testimonials = query.order_by(desc(Testimonial.created_at)).limit(100).all()

    return [
        AdminTestimonialItem(
            id=t.id,
            user_id=t.user_id,
            user_name=t.user.name,
            business_name=t.user.business_name,
            email=t.user.email,
            text=t.text,
            rating=t.rating,
            approved=t.approved,
            featured=t.featured,
            created_at=t.created_at,
        )
        for t in testimonials
    ]


class TestimonialUpdateIn(BaseModel):
    approved: bool | None = None
    featured: bool | None = None


@router.patch("/testimonials/{testimonial_id}")
def update_testimonial(
    testimonial_id: int,
    body: TestimonialUpdateIn,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Approve, feature, or reject a testimonial."""
    from app.models.models import Testimonial

    testimonial = db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    if body.approved is not None:
        testimonial.approved = body.approved
    if body.featured is not None:
        testimonial.featured = body.featured

    db.commit()

    log_audit_event(
        "admin.testimonials.update",
        user_id=admin_user.id,
        testimonial_id=testimonial_id,
        approved=testimonial.approved,
        featured=testimonial.featured,
    )
    logger.info(
        "Admin %s updated testimonial %d: approved=%s featured=%s",
        admin_user.id, testimonial_id, testimonial.approved, testimonial.featured,
    )

    return {
        "id": testimonial_id,
        "approved": testimonial.approved,
        "featured": testimonial.featured,
        "message": "Testimonial updated",
    }


@router.delete("/testimonials/{testimonial_id}")
def delete_testimonial(
    testimonial_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Delete a testimonial."""
    from app.models.models import Testimonial

    testimonial = db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    db.delete(testimonial)
    db.commit()

    log_audit_event(
        "admin.testimonials.delete",
        user_id=admin_user.id,
        testimonial_id=testimonial_id,
    )
    return {"message": "Testimonial deleted"}


@router.post("/testimonials/send-requests")
def send_testimonial_requests(
    admin_user=Depends(get_current_admin),
) -> dict:
    """Trigger feedback collection emails to eligible users now."""
    from app.workers.celery_app import celery_app as celery

    log_audit_event(
        "admin.testimonials.send_requests",
        user_id=admin_user.id,
    )
    try:
        celery.send_task("feedback.collect_user_feedback")
    except Exception:
        raise HTTPException(status_code=503, detail="Worker unavailable, try again later")
    return {"message": "Feedback request emails queued"}


# =============================================================================
# STOREFRONT MODERATION & METRICS (Trust & Safety)
# =============================================================================

STORE_STATUSES = {"active", "suspended", "delisted"}


class StorefrontMetricItem(BaseModel):
    id: int
    name: str
    business_name: str | None
    slug: str | None
    storefront_enabled: bool
    store_status: str
    store_status_reason: str | None
    store_status_at: str | None

    # Discovery / catalog
    views: int
    products_total: int
    products_active: int
    has_logo: bool
    has_description: bool
    has_location: bool
    online_payments_enabled: bool

    # Reputation
    reviews_count: int
    reviews_avg: float | None

    # Commercial
    sales_count: int
    gmv: float
    last_sale_at: str | None
    days_since_last_sale: int | None
    created_at: str

    # Owner trust (link to anti-fraud)
    owner_flagged: bool
    owner_risk_score: int

    # Derived
    quality_score: int  # 0-100
    risk_flags: list[str]


class StorefrontListResponse(BaseModel):
    storefronts: list[StorefrontMetricItem]
    total: int
    page: int
    page_size: int
    # Aggregate counts for the dashboard header
    counts: dict[str, int]


@router.get("/storefronts", response_model=StorefrontListResponse)
def list_storefronts(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    status_filter: str = Query("all", pattern="^(all|active|suspended|delisted)$"),
    criteria: str | None = Query(
        None,
        pattern="^(no_products|no_logo|no_online_payments|no_sales|low_rating|thin_profile|flagged_owner)$",
    ),
    sort_by: str = Query(
        "quality_score",
        pattern="^(quality_score|views|gmv|sales_count|products_active|reviews_count|created_at|name)$",
    ),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    search: str | None = Query(None, max_length=100),
    _admin: Any = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Per-storefront metrics + moderation intelligence.

    Surfaces catalog, reputation and sales metrics for every business that has
    opted into a public storefront, plus auto risk-flags for stores that fail our
    quality/trust criteria so an admin can decide whether to suspend or delist.
    """
    from app.models.inventory_models import Product
    from app.models.models import Invoice

    now = dt.datetime.now(dt.timezone.utc)

    # Base: anyone who has ever turned on a storefront (regardless of status, so
    # suspended/delisted stores remain visible to admins).
    q = db.query(models.User).filter(models.User.storefront_slug.isnot(None))

    if status_filter != "all":
        q = q.filter(models.User.store_status == status_filter)

    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            (models.User.name.ilike(term))
            | (models.User.business_name.ilike(term))
            | (models.User.storefront_slug.ilike(term))
        )

    owners = q.limit(ADMIN_LIST_CAP).all()
    owner_ids = [u.id for u in owners]

    # ── Aggregate products per owner ──
    prod_map: dict[int, Any] = {}
    review_map: dict[int, Any] = {}
    sales_map: dict[int, Any] = {}
    if owner_ids:
        prod_rows = (
            db.query(
                Product.user_id,
                func.count(Product.id).label("total"),
                func.count(case((Product.is_active.is_(True), 1))).label("active"),
            )
            .filter(Product.user_id.in_(owner_ids))
            .group_by(Product.user_id)
            .all()
        )
        prod_map = {r.user_id: r for r in prod_rows}

        review_rows = (
            db.query(
                models.StorefrontReview.user_id,
                func.count(models.StorefrontReview.id).label("cnt"),
                func.avg(models.StorefrontReview.rating).label("avg"),
            )
            .filter(
                models.StorefrontReview.user_id.in_(owner_ids),
                models.StorefrontReview.approved.is_(True),
            )
            .group_by(models.StorefrontReview.user_id)
            .all()
        )
        review_map = {r.user_id: r for r in review_rows}

        # Sales proxy: paid revenue invoices (this is how a store makes money).
        sales_rows = (
            db.query(
                Invoice.issuer_id,
                func.count(Invoice.id).label("cnt"),
                func.sum(Invoice.amount).label("gmv"),
                func.max(Invoice.created_at).label("last_sale"),
            )
            .filter(
                Invoice.issuer_id.in_(owner_ids),
                Invoice.invoice_type == "revenue",
                Invoice.status == "paid",
            )
            .group_by(Invoice.issuer_id)
            .all()
        )
        sales_map = {r.issuer_id: r for r in sales_rows}

    items: list[StorefrontMetricItem] = []
    for u in owners:
        p = prod_map.get(u.id)
        r = review_map.get(u.id)
        s = sales_map.get(u.id)

        products_total = int(p.total) if p else 0
        products_active = int(p.active) if p else 0
        reviews_count = int(r.cnt) if r else 0
        reviews_avg = round(float(r.avg), 1) if r and r.avg is not None else None
        sales_count = int(s.cnt) if s else 0
        gmv = round(float(s.gmv or 0), 2) if s else 0.0
        last_sale = s.last_sale if s else None
        if last_sale is not None and getattr(last_sale, "tzinfo", None) is None:
            last_sale = last_sale.replace(tzinfo=dt.timezone.utc)
        days_since_sale = (now - last_sale).days if last_sale else None

        has_logo = bool(u.logo_url)
        has_description = bool(u.storefront_description)
        has_location = bool(u.storefront_address or u.storefront_city)
        online = bool(u.paystack_subaccount_active and u.paystack_subaccount_code)

        # ── Risk flags (delisting criteria) ──
        flags: list[str] = []
        if products_active == 0:
            flags.append("no_products")
        if not has_logo:
            flags.append("no_logo")
        if not online:
            flags.append("no_online_payments")
        if sales_count == 0:
            flags.append("no_sales")
        if reviews_count >= 3 and reviews_avg is not None and reviews_avg < 2.5:
            flags.append("low_rating")
        if not has_description and not has_location:
            flags.append("thin_profile")
        if u.flagged_for_review:
            flags.append("flagged_owner")

        # ── Quality score (0-100) ──
        score = 50
        score += 15 if products_active >= 3 else (5 if products_active >= 1 else -20)
        score += 10 if has_logo else -10
        score += 10 if online else -15
        score += 15 if sales_count >= 5 else (8 if sales_count >= 1 else -10)
        if reviews_count >= 3:
            if reviews_avg and reviews_avg >= 4:
                score += 10
            elif reviews_avg and reviews_avg < 2.5:
                score -= 15
        score += 5 if (u.storefront_views or 0) >= 20 else 0
        if has_description or has_location:
            score += 5
        if u.flagged_for_review:
            score -= 20
        if u.store_status != "active":
            score -= 15
        score = max(0, min(100, score))

        items.append(
            StorefrontMetricItem(
                id=u.id,
                name=u.name,
                business_name=u.business_name,
                slug=u.storefront_slug,
                storefront_enabled=bool(u.storefront_enabled),
                store_status=u.store_status,
                store_status_reason=u.store_status_reason,
                store_status_at=u.store_status_at.isoformat() if u.store_status_at else None,
                views=u.storefront_views or 0,
                products_total=products_total,
                products_active=products_active,
                has_logo=has_logo,
                has_description=has_description,
                has_location=has_location,
                online_payments_enabled=online,
                reviews_count=reviews_count,
                reviews_avg=reviews_avg,
                sales_count=sales_count,
                gmv=gmv,
                last_sale_at=last_sale.isoformat() if last_sale else None,
                days_since_last_sale=days_since_sale,
                created_at=u.created_at.isoformat(),
                owner_flagged=bool(u.flagged_for_review),
                owner_risk_score=int(u.risk_score or 0),
                quality_score=score,
                risk_flags=flags,
            )
        )

    # Aggregate status counts across the (unpaginated) matched set.
    counts = {
        "total": len(items),
        "active": sum(1 for i in items if i.store_status == "active"),
        "suspended": sum(1 for i in items if i.store_status == "suspended"),
        "delisted": sum(1 for i in items if i.store_status == "delisted"),
        "low_quality": sum(1 for i in items if i.quality_score < 40),
        # Live = discoverable in public global search (same gate as the marketplace).
        "live": sum(
            1
            for i in items
            if i.store_status == "active"
            and i.has_logo
            and i.online_payments_enabled
            and i.products_active >= 1
        ),
    }

    if criteria:
        items = [i for i in items if criteria in i.risk_flags]

    reverse = sort_order == "desc"
    key_map = {
        "quality_score": lambda x: x.quality_score,
        "views": lambda x: x.views,
        "gmv": lambda x: x.gmv,
        "sales_count": lambda x: x.sales_count,
        "products_active": lambda x: x.products_active,
        "reviews_count": lambda x: x.reviews_count,
        "created_at": lambda x: x.created_at,
        "name": lambda x: (x.business_name or x.name).lower(),
    }
    items.sort(key=key_map[sort_by], reverse=reverse)

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return StorefrontListResponse(
        storefronts=page_items,
        total=total,
        page=page,
        page_size=page_size,
        counts=counts,
    )


class StorefrontStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|suspended|delisted)$")
    reason: str | None = Field(None, max_length=255)


@router.post("/storefronts/{user_id}/status")
def set_storefront_status(
    user_id: int,
    payload: StorefrontStatusUpdate,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Suspend, delist or reinstate a business's public storefront.

    - ``suspended`` / ``delisted`` immediately remove the store from the public
      directory and make its store page + ordering return 404.
    - ``active`` reinstates it.

    The owner's account, invoices and data are untouched — this only controls the
    public storefront's visibility.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_status = user.store_status
    user.store_status = payload.status
    user.store_status_reason = (payload.reason or None) if payload.status != "active" else None
    user.store_status_at = dt.datetime.now(dt.timezone.utc)
    user.store_status_by_id = admin_user.id
    db.commit()

    log_audit_event(
        "admin.storefronts.status",
        user_id=admin_user.id,
        target_user_id=user_id,
        old_status=old_status,
        new_status=payload.status,
        reason=payload.reason,
    )
    logger.info(
        "Admin %s changed storefront status for user %s: %s -> %s (%s)",
        admin_user.id, user_id, old_status, payload.status, payload.reason,
    )

    return {
        "user_id": user_id,
        "store_status": user.store_status,
        "store_status_reason": user.store_status_reason,
        "message": f"Storefront {payload.status}",
    }


# =============================================================================
# TRUST & SAFETY — ANTI-FRAUD REVIEW
# =============================================================================

class RiskUserItem(BaseModel):
    id: int
    name: str
    business_name: str | None
    phone: str | None
    email: str | None
    created_at: str
    signup_source: str | None
    signup_ip: str | None
    signup_device_id: str | None
    signup_user_agent: str | None
    risk_score: int
    risk_signals: list[str]
    flagged_for_review: bool
    store_status: str
    storefront_slug: str | None
    linked_account_count: int


class RiskListResponse(BaseModel):
    users: list[RiskUserItem]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


@router.get("/fraud/flagged", response_model=RiskListResponse)
def list_flagged_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    view: str = Query("flagged", pattern="^(flagged|risky|all)$"),
    min_score: int = Query(0, ge=0, le=100),
    search: str | None = Query(None, max_length=100),
    _admin: Any = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List accounts that need Trust & Safety attention.

    ``view=flagged`` (default) shows accounts flagged at signup; ``risky`` shows
    any account with a non-trivial risk score; ``all`` ignores the risk gate and
    is mostly useful with a search term. Each row includes how many other
    accounts share the same IP or device fingerprint (duplicate-account cluster).
    """
    from app.services.fraud_service import FLAG_SCORE

    q = db.query(models.User)
    if view == "flagged":
        q = q.filter(models.User.flagged_for_review.is_(True))
    elif view == "risky":
        q = q.filter(models.User.risk_score >= max(min_score, 1))
    if min_score:
        q = q.filter(models.User.risk_score >= min_score)

    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            (models.User.name.ilike(term))
            | (models.User.business_name.ilike(term))
            | (models.User.phone.ilike(term))
            | (models.User.email.ilike(term))
            | (models.User.signup_ip.ilike(term))
            | (models.User.signup_device_id.ilike(term))
        )

    rows = q.order_by(desc(models.User.risk_score), desc(models.User.created_at)).limit(ADMIN_LIST_CAP).all()

    # Pre-compute linked-account counts for the visible page only (cheaper).
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]

    # Count accounts sharing IP / device across the whole table for each row.
    def _linked_count(u: models.User) -> int:
        from sqlalchemy import or_

        conds = []
        if u.signup_ip:
            conds.append(models.User.signup_ip == u.signup_ip)
        if u.signup_device_id:
            conds.append(models.User.signup_device_id == u.signup_device_id)
        if not conds:
            return 0
        return (
            db.query(func.count(models.User.id))
            .filter(or_(*conds), models.User.id != u.id)
            .scalar()
        ) or 0

    users = [
        RiskUserItem(
            id=u.id,
            name=u.name,
            business_name=u.business_name,
            phone=u.phone,
            email=u.email,
            created_at=u.created_at.isoformat(),
            signup_source=u.signup_source,
            signup_ip=u.signup_ip,
            signup_device_id=u.signup_device_id,
            signup_user_agent=u.signup_user_agent,
            risk_score=int(u.risk_score or 0),
            risk_signals=list(u.risk_signals or []),
            flagged_for_review=bool(u.flagged_for_review),
            store_status=u.store_status,
            storefront_slug=u.storefront_slug,
            linked_account_count=_linked_count(u),
        )
        for u in page_rows
    ]

    counts = {
        "flagged": db.query(func.count(models.User.id))
        .filter(models.User.flagged_for_review.is_(True))
        .scalar()
        or 0,
        "high_risk": db.query(func.count(models.User.id))
        .filter(models.User.risk_score >= FLAG_SCORE)
        .scalar()
        or 0,
    }

    return RiskListResponse(
        users=users,
        total=total,
        page=page,
        page_size=page_size,
        counts=counts,
    )


@router.get("/fraud/{user_id}/linked")
def get_linked_accounts(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: Any = Depends(get_current_admin),
) -> dict:
    """List other accounts that share this user's IP or device fingerprint."""
    from app.services.fraud_service import linked_account_ids

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ids = linked_account_ids(db, user)
    linked = (
        db.query(models.User).filter(models.User.id.in_(ids)).all() if ids else []
    )
    return {
        "user_id": user_id,
        "shared_ip": user.signup_ip,
        "shared_device_id": user.signup_device_id,
        "linked": [
            {
                "id": lu.id,
                "name": lu.name,
                "business_name": lu.business_name,
                "phone": lu.phone,
                "email": lu.email,
                "created_at": lu.created_at.isoformat(),
                "risk_score": int(lu.risk_score or 0),
                "flagged_for_review": bool(lu.flagged_for_review),
                "store_status": lu.store_status,
                "same_ip": bool(user.signup_ip and lu.signup_ip == user.signup_ip),
                "same_device": bool(
                    user.signup_device_id and lu.signup_device_id == user.signup_device_id
                ),
            }
            for lu in linked
        ],
    }


class RiskReviewAction(BaseModel):
    action: str = Field(..., pattern="^(clear|flag|ban)$")
    reason: str | None = Field(None, max_length=255)


@router.post("/fraud/{user_id}/review")
def review_flagged_user(
    user_id: int,
    payload: RiskReviewAction,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Resolve a Trust & Safety review for an account.

    - ``clear`` — mark the account as legitimate (unflag).
    - ``flag``  — flag the account for review.
    - ``ban``   — flag the account AND delist its public storefront.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.action == "clear":
        user.flagged_for_review = False
    elif payload.action == "flag":
        user.flagged_for_review = True
    elif payload.action == "ban":
        user.flagged_for_review = True
        user.store_status = "delisted"
        user.store_status_reason = payload.reason or "Trust & Safety: banned"
        user.store_status_at = dt.datetime.now(dt.timezone.utc)
        user.store_status_by_id = admin_user.id

    db.commit()

    log_audit_event(
        "admin.fraud.review",
        user_id=admin_user.id,
        target_user_id=user_id,
        review_action=payload.action,
        reason=payload.reason,
    )
    logger.info(
        "Admin %s ran fraud review '%s' on user %s (%s)",
        admin_user.id, payload.action, user_id, user.email or user.phone,
    )

    return {
        "user_id": user_id,
        "flagged_for_review": user.flagged_for_review,
        "store_status": user.store_status,
        "message": f"Review action '{payload.action}' applied",
    }


# ── Escrow disputes (buyer protection) ─────────────────────────────────

class DisputeItem(BaseModel):
    escrow_id: int
    invoice_id: int
    invoice_public_id: str | None = None
    status: str
    seller_id: int
    seller_name: str | None = None
    seller_business: str | None = None
    seller_store_status: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    gross_naira: float
    payout_naira: float
    dispute_reason: str | None = None
    held_for_review: bool = False
    review_reason: str | None = None
    # Seller-submitted delivery proof (defends against false non-delivery claims).
    delivered_at: dt.datetime | None = None
    delivery_proof_note: str | None = None
    delivery_proof_url: str | None = None
    # Seller DISPATCH proof (marked sent out) — the earlier handoff evidence.
    dispatched_at: dt.datetime | None = None
    dispatch_tracking: str | None = None
    dispatch_note: str | None = None
    dispatch_proof_url: str | None = None
    # Where the order was to be delivered (GPS maps link + landmark), captured at
    # order time — lets the reviewer see the delivery destination.
    delivery_location: str | None = None
    # Buyer reputation (global, by phone) — spot serial false-disputers.
    buyer_disputes: int = 0
    buyer_false_disputes: int = 0
    buyer_flagged: bool = False
    # Seller off-platform-messaging attempts (contact/account leak or payment push).
    seller_circumvention_attempts: int = 0
    # Payout state derived from stored fields (no live API call):
    # none | processing | paid | refunded. Use the live payout-status endpoint
    # to confirm the provider's transfer state (queued/paid/failed) on demand.
    payout_state: str = "none"
    transfer_reference: str | None = None
    # For a held order, when it will auto-pay (later of the dispute-window end and
    # the T+1 settlement time). Lets the panel show "pays out after X" instead of
    # a bare "No payout yet".
    payout_eta: dt.datetime | None = None
    disputed_at: dt.datetime | None = None
    created_at: dt.datetime | None = None


class DisputeListResponse(BaseModel):
    disputes: list[DisputeItem]
    total: int


def _derive_payout_state(e: "models.StorefrontOrderEscrow") -> str:
    """Cheap payout state from stored escrow fields (no provider API call).
    none | scheduled | processing | paid | refunded."""
    if e.status == "released":
        return "paid"
    if e.status == "refunded":
        return "refunded"
    if e.transfer_reference:
        return "processing"  # a payout was initiated and is in flight
    if e.status == "held":
        return "scheduled"  # cleared/holding — auto-pays after window + T+1 settlement
    return "none"


def _payout_eta(e: "models.StorefrontOrderEscrow") -> "dt.datetime | None":
    """Earliest a held order will auto-pay: the later of its dispute-window end and
    the T+1 settlement time (payouts never run before funds have settled)."""
    if e.status != "held":
        return None
    times = [
        t for t in (getattr(e, "release_due_at", None), getattr(e, "settle_at", None)) if t
    ]
    return max(times) if times else None


class FlaggedMessageItem(BaseModel):
    id: int
    escrow_id: int
    seller_id: int
    seller_business: str | None = None
    sender_role: str
    body_raw: str  # exact text kept for adjudication
    flag_reasons: str | None = None
    blocked: bool = False
    created_at: dt.datetime | None = None


class FlaggedMessageListResponse(BaseModel):
    messages: list[FlaggedMessageItem]
    total: int


@router.get("/flagged-messages", response_model=FlaggedMessageListResponse)
def list_flagged_messages(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    limit: int = Query(200, ge=1, le=ADMIN_LIST_CAP),
) -> FlaggedMessageListResponse:
    """Order messages flagged for circumvention (masked contact/account, or an
    off-platform payment push), newest first. ``body_raw`` is the exact text kept
    for adjudication; ``blocked`` messages were never delivered to the recipient.
    """
    q = (
        db.query(models.OrderMessage, models.User)
        .join(
            models.StorefrontOrderEscrow,
            models.OrderMessage.escrow_id == models.StorefrontOrderEscrow.id,
        )
        .join(models.User, models.StorefrontOrderEscrow.seller_id == models.User.id)
        .filter(models.OrderMessage.flagged.is_(True))
    )
    total = q.count()
    rows = q.order_by(desc(models.OrderMessage.id)).limit(limit).all()

    log_audit_event("admin.flagged_messages.list", user_id=admin_user.id)

    return FlaggedMessageListResponse(
        messages=[
            FlaggedMessageItem(
                id=m.id,
                escrow_id=m.escrow_id,
                seller_id=seller.id,
                seller_business=getattr(seller, "business_name", None),
                sender_role=m.sender_role,
                body_raw=m.body_raw,
                flag_reasons=m.flag_reasons,
                blocked=bool(m.blocked),
                created_at=m.created_at,
            )
            for (m, seller) in rows
        ],
        total=total,
    )


@router.get("/disputes", response_model=DisputeListResponse)
def list_disputes(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    status_filter: str = Query("disputed", pattern="^(disputed|held|refunded|released|review|all)$"),
    limit: int = Query(200, ge=1, le=ADMIN_LIST_CAP),
) -> DisputeListResponse:
    """List storefront escrow orders for the Trust & Safety review queue.

    Defaults to open disputes; ``status_filter=review`` shows collusion/anomaly
    holds; ``status_filter=all`` shows every escrow.
    """
    q = (
        db.query(models.StorefrontOrderEscrow, models.User, models.Invoice, models.Customer)
        .join(models.User, models.StorefrontOrderEscrow.seller_id == models.User.id)
        .join(models.Invoice, models.StorefrontOrderEscrow.invoice_id == models.Invoice.id)
        .outerjoin(models.Customer, models.Invoice.customer_id == models.Customer.id)
    )
    if status_filter == "review":
        q = q.filter(
            models.StorefrontOrderEscrow.held_for_review.is_(True),
            # Unpaid ('pending') orders never moved money — keep them out of the
            # review queue even if flagged, so an abandoned checkout can't put a
            # seller in front of Trust & Safety.
            models.StorefrontOrderEscrow.status != "pending",
        )
    elif status_filter == "all":
        # 'All' means all REAL (paid) orders — exclude unpaid pending rows.
        q = q.filter(models.StorefrontOrderEscrow.status != "pending")
    else:
        q = q.filter(models.StorefrontOrderEscrow.status == status_filter)

    total = q.count()
    rows = (
        q.order_by(desc(models.StorefrontOrderEscrow.disputed_at), desc(models.StorefrontOrderEscrow.id))
        .limit(limit)
        .all()
    )

    log_audit_event("admin.disputes.list", user_id=admin_user.id, status_filter=status_filter)

    from app.services.escrow_service import get_buyer_reputation
    from app.api.routes_storefront import _presign

    disputes = []
    for (e, seller, inv, cust) in rows:
        rep = get_buyer_reputation(db, cust.phone) if cust else None
        disputes.append(
            DisputeItem(
                escrow_id=e.id,
                invoice_id=e.invoice_id,
                invoice_public_id=getattr(inv, "invoice_id", None),
                status=e.status,
                seller_id=seller.id,
                seller_name=seller.name,
                seller_business=seller.business_name,
                seller_store_status=seller.store_status,
                customer_name=cust.name if cust else None,
                customer_phone=cust.phone if cust else None,
                gross_naira=round((e.gross_kobo or 0) / 100, 2),
                payout_naira=round((e.payout_kobo or 0) / 100, 2),
                dispute_reason=e.dispute_reason,
                held_for_review=bool(e.held_for_review),
                review_reason=e.review_reason,
                delivered_at=e.seller_marked_delivered_at,
                delivery_proof_note=e.delivery_proof_note,
                delivery_proof_url=_presign(e.delivery_proof_url),
                dispatched_at=e.seller_dispatched_at,
                dispatch_tracking=e.dispatch_tracking,
                dispatch_note=e.dispatch_note,
                dispatch_proof_url=_presign(e.dispatch_proof_url),
                delivery_location=getattr(inv, "notes", None),
                buyer_disputes=rep.disputes if rep else 0,
                buyer_false_disputes=rep.false_disputes if rep else 0,
                buyer_flagged=bool(rep.flagged) if rep else False,
                seller_circumvention_attempts=seller.circumvention_attempts or 0,
                payout_state=_derive_payout_state(e),
                transfer_reference=e.transfer_reference,
                payout_eta=_payout_eta(e),
                disputed_at=e.disputed_at,
                created_at=e.created_at,
            )
        )
    return DisputeListResponse(disputes=disputes, total=total)


class DisputeResolveAction(BaseModel):
    action: str = Field(..., pattern="^(refund|release)$")
    suspend_seller: bool = False
    reason: str | None = Field(None, max_length=255)
    otp: str | None = Field(None, max_length=12)  # step-up code for high-value actions
    block_card: bool = False  # on refund: block the funding card (card-fraud)


class RetryPayoutIn(BaseModel):
    otp: str | None = Field(None, max_length=12)  # step-up code for high-value payouts


_ADMIN_MONEY_OTP_PURPOSE = "admin_money_action"


def _require_super_admin(admin_user) -> None:
    """Restrict money movement and destructive account changes to super admins.
    A lower-privilege support admin can view/triage but can't refund, pay out, or
    change a user's plan even with a valid session."""
    if not getattr(admin_user, "is_super_admin", False):
        raise HTTPException(status_code=403, detail="This action requires a super-admin.")


def _require_money_stepup(admin_user, amount_naira: float, otp: str | None) -> None:
    """Require a fresh step-up OTP for money moves above the configured threshold.

    Defends against a stolen admin session/cookie moving large sums: even with a
    valid session, a big refund/release needs a code sent to the admin's email.
    """
    from app.core.config import settings

    if amount_naira < settings.ESCROW_ADMIN_STEPUP_NAIRA:
        return
    email = getattr(admin_user, "email", None)
    from app.services.otp_service import OTPService

    if not otp or not email or not OTPService().verify_otp(
        email, otp, purpose=_ADMIN_MONEY_OTP_PURPOSE
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                f"This action moves ₦{amount_naira:,.0f}. Request a confirmation "
                "code (step-up) and include it to proceed."
            ),
        )


@router.post("/disputes/{escrow_id}/step-up-otp")
def request_dispute_stepup_otp(
    escrow_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Send a step-up confirmation code to the admin's email for a high-value
    refund/release on this order."""
    email = getattr(admin_user, "email", None)
    if not email:
        raise HTTPException(status_code=400, detail="Admin has no email for step-up.")
    from app.services.otp_service import OTPService

    OTPService().send_code(email, purpose=_ADMIN_MONEY_OTP_PURPOSE)
    log_audit_event("admin.disputes.stepup_requested", user_id=admin_user.id, escrow_id=escrow_id)
    return {"ok": True, "detail": "Confirmation code sent to your admin email."}


@router.post("/disputes/{escrow_id}/resolve")
@limiter.limit("20/minute")
def resolve_dispute(
    request: Request,
    escrow_id: int,
    payload: DisputeResolveAction,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Resolve an escrow dispute.

    - ``refund``  — return the money to the buyer (Paystack Refund). Optionally
      suspend the seller's storefront (``suspend_seller``).
    - ``release`` — side with the seller and pay them out (Paystack Transfer).
    """
    _require_super_admin(admin_user)
    from app.services.escrow_service import EscrowError, refund_escrow, release_escrow

    escrow = (
        db.query(models.StorefrontOrderEscrow)
        .filter(models.StorefrontOrderEscrow.id == escrow_id)
        .first()
    )
    if not escrow:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if escrow.status in ("refunded", "released"):
        raise HTTPException(
            status_code=409, detail=f"This order is already {escrow.status}."
        )

    amount_naira = round((escrow.gross_kobo or 0) / 100, 2)

    # Step-up gate. For refunds we also fold in the admin's rolling 24h refund
    # total: even a small refund needs a fresh OTP once cumulative refunds cross
    # the threshold — stops a hijacked session scripting many sub-threshold
    # refunds to drain funds.
    stepup_amount = amount_naira
    if payload.action == "refund":
        from app.services.admin_refund_guard import refund_total_24h

        stepup_amount = max(
            amount_naira, refund_total_24h(admin_user.id) + amount_naira
        )
    _require_money_stepup(admin_user, stepup_amount, payload.otp)

    # An admin decision clears any anti-fraud review hold so the action can go
    # through (release_escrow refuses to pay a held_for_review order otherwise).
    if escrow.held_for_review:
        escrow.held_for_review = False
        db.commit()

    if payload.action == "refund":
        # refund_escrow only refunds held/disputed rows; nudge to disputed first.
        try:
            refund_escrow(db, escrow, reason=payload.reason or "admin dispute resolution")
        except EscrowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if payload.suspend_seller:
            seller = (
                db.query(models.User)
                .filter(models.User.id == escrow.seller_id)
                .first()
            )
            if seller:
                seller.flagged_for_review = True
                seller.store_status = "delisted"
                seller.store_status_reason = (
                    payload.reason or "Trust & Safety: buyer-protection dispute"
                )
                seller.store_status_at = dt.datetime.now(dt.timezone.utc)
                seller.store_status_by_id = admin_user.id
                db.commit()
        # Card-fraud: block the funding card from new orders for a period.
        if payload.block_card and getattr(escrow, "card_fingerprint", None):
            try:
                from app.services.card_risk import block_card

                block_card(
                    db,
                    escrow.card_fingerprint,
                    reason=payload.reason or "admin refund: card fraud",
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to block card for escrow %s", escrow_id)
        # Count this refund toward the admin's rolling 24h step-up window.
        from app.services.admin_refund_guard import record_refund

        record_refund(admin_user.id, amount_naira)
        result_status = "refunded"
    else:  # release
        # Releasing requires a 'held' row; a disputed row is flipped back first.
        was_disputed = escrow.status == "disputed"
        if escrow.status == "disputed":
            escrow.status = "held"
            db.commit()
        try:
            released_now = release_escrow(
                db, escrow, reason=payload.reason or "admin dispute resolution"
            )
        except EscrowError as exc:
            # Restore disputed state so it stays in the queue for a retry.
            escrow.status = "disputed"
            db.commit()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        # A Flutterwave payout is often accepted as 'queued' and confirmed
        # asynchronously — the row stays 'held' until the reconcile worker
        # confirms it, so report the real state instead of a premature "released".
        result_status = "released" if released_now else "release_pending"

        # Releasing a DISPUTED order = admin sided with the seller → the buyer's
        # "not delivered" claim was false. Count it against the buyer.
        if was_disputed:
            try:
                from app.services.escrow_service import record_buyer_false_dispute

                buyer = (
                    db.query(models.Customer)
                    .join(models.Invoice, models.Invoice.customer_id == models.Customer.id)
                    .filter(models.Invoice.id == escrow.invoice_id)
                    .first()
                )
                record_buyer_false_dispute(db, buyer.phone if buyer else None)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to record false dispute for escrow %s", escrow_id)

    log_audit_event(
        "admin.disputes.resolve",
        user_id=admin_user.id,
        escrow_id=escrow_id,
        resolution=payload.action,
        suspend_seller=payload.suspend_seller,
        reason=payload.reason,
    )
    logger.info(
        "Admin %s resolved dispute %s -> %s (suspend=%s)",
        admin_user.id, escrow_id, result_status, payload.suspend_seller,
    )
    message = None
    if result_status == "release_pending":
        message = (
            "Cleared for the seller. Payouts settle on our T+1 cadence, so this "
            "pays out on the next daily settlement run (never same-day) and then "
            "moves to Released."
        )
    return {
        "escrow_id": escrow_id,
        "status": result_status,
        "action": payload.action,
        "message": message,
    }


@router.get("/disputes/{escrow_id}/payout-status")
def dispute_payout_status(
    escrow_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Live payout state for one escrow's seller transfer.

    Confirms the actual provider transfer state (paid/pending/failed) on demand —
    used by the disputes panel so an admin can see whether a release actually
    landed without leaving the page. Normalizes provider values to:
    paid | pending | failed | unknown | refunded | none.
    """
    escrow = (
        db.query(models.StorefrontOrderEscrow)
        .filter(models.StorefrontOrderEscrow.id == escrow_id)
        .first()
    )
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow not found")

    if escrow.status == "released":
        return {"state": "paid", "reference": escrow.transfer_reference}
    if escrow.status == "refunded":
        return {"state": "refunded", "reference": escrow.refund_reference}
    if not escrow.transfer_reference:
        return {"state": "none", "reference": None}

    from app.services.escrow_service import _collector_for_charge
    from app.services.payouts import get_payout_provider, get_payout_provider_named

    if escrow.charge_reference:
        provider = get_payout_provider_named(_collector_for_charge(db, escrow.charge_reference))
    else:
        provider = get_payout_provider()

    try:
        raw = (provider.transfer_status(escrow.transfer_reference) or "unknown").lower()
    except Exception:  # noqa: BLE001 — never let a status poll 500 the panel
        logger.exception("Payout status poll failed for escrow %s", escrow_id)
        raw = "unknown"

    state = "paid" if raw == "successful" else raw  # normalize for the UI

    # If the provider confirms the transfer landed, finalize the hold now so the
    # admin doesn't wait for the reconcile worker. This is safe/idempotent —
    # release_escrow only marks 'released' on a confirmed success and never sends
    # a new transfer from here.
    if state == "paid" and escrow.status == "held":
        try:
            from app.services.escrow_service import release_escrow

            if release_escrow(db, escrow, reason="admin payout-status reconcile"):
                state = "paid"
        except Exception:  # noqa: BLE001 — reporting must not fail on reconcile
            logger.exception("Reconcile-on-status-check failed for escrow %s", escrow_id)

    log_audit_event(
        "admin.disputes.payout_status",
        user_id=admin_user.id,
        escrow_id=escrow_id,
        payout_state=state,
    )
    return {
        "state": state,
        "reference": escrow.transfer_reference,
        "provider": provider.name,
        "escrow_status": escrow.status,
    }


@router.post("/disputes/{escrow_id}/retry-payout")
def retry_dispute_payout(
    escrow_id: int,
    payload: RetryPayoutIn | None = Body(default=None),
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """Force a fresh seller payout on the CURRENT rail for a stuck hold.

    Use when a release is stuck (e.g. an earlier attempt went out on the wrong
    rail and failed, leaving a reference the current provider reports as
    'unknown'). Safe: if the current rail already shows the transfer as paid or
    in flight, it finalizes/waits instead of sending a second payout; otherwise
    it clears the void reference and sends a fresh transfer on the correct rail.
    """
    _require_super_admin(admin_user)
    from app.services.escrow_service import EscrowError, _collector_for_charge, release_escrow
    from app.services.payouts import get_payout_provider, get_payout_provider_named

    escrow = (
        db.query(models.StorefrontOrderEscrow)
        .filter(models.StorefrontOrderEscrow.id == escrow_id)
        .first()
    )
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow not found")
    if escrow.status == "released":
        return {"state": "paid", "escrow_status": "released"}
    if escrow.status != "held":
        raise HTTPException(status_code=409, detail="Only a held order can be retried.")
    if escrow.held_for_review:
        raise HTTPException(status_code=409, detail="Order is under review — resolve that first.")

    # High-value payout → require a fresh step-up OTP (stolen-session defense).
    _require_money_stepup(
        admin_user,
        round((escrow.payout_kobo or 0) / 100, 2),
        payload.otp if payload else None,
    )

    if escrow.charge_reference:
        provider = get_payout_provider_named(_collector_for_charge(db, escrow.charge_reference))
    else:
        provider = get_payout_provider()

    # Never send a second payout if the current rail already has this transfer.
    if escrow.transfer_reference and escrow.transfer_provider == provider.name:
        try:
            cur = (provider.transfer_status(escrow.transfer_reference) or "unknown").lower()
        except Exception:  # noqa: BLE001
            cur = "unknown"
        if cur == "successful":
            release_escrow(db, escrow, reason="admin retry (already paid)")
            return {"state": "paid", "escrow_status": escrow.status}
        if cur == "pending":
            return {
                "state": "pending",
                "escrow_status": escrow.status,
                "message": "A payout is already in flight on this rail — it will confirm shortly.",
            }

    # Clear the void reference (from a failed/other-rail attempt) and resend fresh.
    escrow.transfer_reference = None
    escrow.transfer_provider = None
    db.commit()
    try:
        released = release_escrow(db, escrow, reason="admin retry payout")
    except EscrowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    log_audit_event(
        "admin.disputes.retry_payout",
        user_id=admin_user.id,
        escrow_id=escrow_id,
        provider=provider.name,
    )
    state = "paid" if released else "release_pending"
    message = None
    if state == "release_pending":
        message = (
            f"Cleared via {provider.name}. Payouts settle on our T+1 cadence, so "
            "this pays out on the next daily settlement run and then moves to Released."
        )
    return {"state": state, "escrow_status": escrow.status, "provider": provider.name, "message": message}

