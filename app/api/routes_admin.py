import datetime as dt
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

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
            "invoice_balance": invoice_balance,
            "invoices_used": invoices_used,
            "pack_purchases": pack_purchases
        }
    }


@router.post("/users/{user_id}/pro-override")
def toggle_pro_override(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> dict:
    """
    Toggle admin-granted PRO feature access for a user.

    This gives the user access to all PRO features (inventory, branding,
    voice, daily summary, etc.) WITHOUT changing their actual plan or
    invoice balance. Invoice packs are NOT included.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_value = not getattr(user, "pro_override", False)
    user.pro_override = new_value
    db.commit()

    change = "granted" if new_value else "revoked"
    log_audit_event(
        "admin.users.pro_override",
        user_id=admin_user.id,
        target_user_id=user_id,
        change=change,
    )
    logger.info(
        "Admin %s %s PRO override for user %s (%s)",
        admin_user.id, change, user_id, user.email or user.phone,
    )

    return {
        "user_id": user_id,
        "pro_override": new_value,
        "message": f"PRO features {change} for {user.name or user.email}",
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
            payout_account_number=account_number,
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
    commission_first: int = 500  # ₦ on first Pro purchase
    commission_recurring: int = 200  # ₦ on purchases 2–3
    commission_months: int = 2  # how many recurring purchases
    commission_perpetual_pct: int = 5  # % on every purchase after recurring window
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
    pro_conversions: int = 0
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
    pro_granted: bool
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
    2. Grants Pro access (pro_override)
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

    # ── 2. Grant Pro subscription (30 days, like a paid Pro Pack) ──
    pro_granted = False
    now = dt.datetime.now(dt.timezone.utc)
    if user.plan != models.SubscriptionPlan.PRO or (
        user.subscription_expires_at and user.subscription_expires_at < now
    ):
        user.plan = models.SubscriptionPlan.PRO
        user.subscription_expires_at = now + dt.timedelta(days=30)
        user.usage_reset_at = now
        user.invoices_this_month = 0
        pro_granted = True

    # Also ensure they have at least 10 invoices
    if user.invoice_balance < 10:
        user.invoice_balance = 10

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
    if pro_granted:
        summary_parts.append("Pro granted")
    if team_created:
        summary_parts.append("team created")
    if invites_sent:
        summary_parts.append(f"{invites_sent} invites sent")
    if wa_sent:
        summary_parts.append("WhatsApp sent")

    return SMEOnboardResult(
        user_id=user.id,
        is_new_user=is_new,
        pro_granted=pro_granted,
        team_created=team_created,
        invites_sent=invites_sent,
        whatsapp_sent=wa_sent,
        message=", ".join(summary_parts) or "User already onboarded",
    )


# ============================================================================
# Platform Metrics
# ============================================================================

class PaidUserInfo(BaseModel):
    """Info about a paid user including referral status."""
    id: int
    name: str
    email: str | None
    phone: str | None
    plan: str
    business_name: str | None
    created_at: dt.datetime
    subscription_started_at: dt.datetime | None
    subscription_expires_at: dt.datetime | None
    was_referred: bool
    referred_by_name: str | None = None
    referred_by_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class PackBuyerInfo(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    business_name: str | None
    invoice_balance: int
    total_packs_bought: int
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
    active_subscriptions: dict[str, int]
    total_customers: int
    paid_users: list[PaidUserInfo]
    pack_buyers: list[PackBuyerInfo]


@router.get("/metrics", response_model=PlatformMetrics)
def get_platform_metrics(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """Get platform-wide metrics for monitoring."""
    from app.models.models import Customer, Invoice
    from app.models.referral_models import Referral, ReferralStatus
    
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
    
    # Subscriptions by plan
    plan_counts = db.query(
        models.User.plan,
        func.count(models.User.id)
    ).group_by(models.User.plan).all()
    
    active_subs = {str(plan.value): count for plan, count in plan_counts}
    
    # Customers
    total_customers = db.query(Customer).count()
    
    # Get invoice pack buyers (FREE users who bought packs)
    pack_buyer_rows = db.query(
        models.User,
        func.count(PaymentTransaction.id).label("pack_count"),
        func.max(PaymentTransaction.created_at).label("last_purchase"),
    ).join(
        PaymentTransaction, PaymentTransaction.user_id == models.User.id
    ).filter(
        models.User.plan == SubscriptionPlan.FREE,
        PaymentTransaction.reference.like("INVPACK-%"),
        PaymentTransaction.status == PaymentStatus.SUCCESS,
    ).group_by(models.User.id).order_by(
        desc(func.max(PaymentTransaction.created_at))
    ).limit(ADMIN_LIST_CAP).all()

    pack_buyers_list: list[PackBuyerInfo] = []
    for user, pack_count, last_purchase in pack_buyer_rows:
        pack_buyers_list.append(PackBuyerInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            business_name=user.business_name,
            invoice_balance=getattr(user, 'invoice_balance', 0),
            total_packs_bought=pack_count,
            last_purchase_date=last_purchase.isoformat() if last_purchase else None,
        ))

    # Get paying users (Pro only — STARTER removed)
    # Auto-downgrade expired subscriptions first
    paid_plans = [SubscriptionPlan.PRO]
    expired_users = db.query(models.User).filter(
        models.User.plan.in_(paid_plans),
        models.User.subscription_expires_at.isnot(None),
        models.User.subscription_expires_at < now,
    ).all()
    for u in expired_users:
        u.plan = SubscriptionPlan.FREE
    if expired_users:
        db.commit()
        logger.info("Auto-downgraded %d expired PRO users to FREE", len(expired_users))

    paid_users_query = db.query(models.User).filter(
        models.User.plan.in_(paid_plans)
    ).order_by(desc(models.User.subscription_started_at)).limit(ADMIN_LIST_CAP).all()
    
    # Build paid users list with referral info
    paid_users_list: list[PaidUserInfo] = []
    for user in paid_users_query:
        # Check if this user was referred
        referral = db.query(Referral).filter(
            Referral.referred_id == user.id,
            Referral.status == ReferralStatus.COMPLETED
        ).first()
        
        was_referred = referral is not None
        referred_by_name = None
        referred_by_id = None
        
        if referral:
            referrer = db.query(models.User).filter(models.User.id == referral.referrer_id).first()
            if referrer:
                referred_by_name = referrer.name
                referred_by_id = referrer.id
        
        paid_users_list.append(PaidUserInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            plan=user.plan.value,
            business_name=user.business_name,
            created_at=user.created_at,
            subscription_started_at=user.subscription_started_at,
            subscription_expires_at=user.subscription_expires_at,
            was_referred=was_referred,
            referred_by_name=referred_by_name,
            referred_by_id=referred_by_id
        ))
    
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
        active_subscriptions=active_subs,
        total_customers=total_customers,
        paid_users=paid_users_list,
        pack_buyers=pack_buyers_list
    )


# =============================================================================
# GROWTH METRICS — MRR, Churn, Activation, Collection Rate, Trends
# =============================================================================

class MonthlyDataPoint(BaseModel):
    month: str  # "2026-01"
    value: float

class ActivationFunnel(BaseModel):
    total_signups: int
    created_first_invoice: int
    received_first_payment: int
    upgraded_to_paid: int

class GrowthMetrics(BaseModel):
    # Revenue
    mrr: float  # Monthly recurring revenue from active subscriptions
    mrr_trend: list[MonthlyDataPoint]  # Last 6 months
    arr: float  # Annualized
    # Churn
    churned_users: int  # Pro expired and not renewed
    churn_rate: float  # % of paid users who churned this month
    # Activation
    activation_funnel: ActivationFunnel
    # Collection
    collection_rate: float  # % of invoices that get paid
    avg_days_to_payment: float | None  # Average days from created → paid
    # Growth trends
    user_growth: list[MonthlyDataPoint]  # New signups per month
    invoice_growth: list[MonthlyDataPoint]  # Invoices created per month
    revenue_growth: list[MonthlyDataPoint]  # Paid revenue per month
    # Engagement
    avg_invoices_per_user: float
    power_users: int  # Users with 10+ invoices this month
    zero_invoice_users: int  # Signed up but never created an invoice
    whatsapp_users: int  # Users with verified WhatsApp phone
    email_only_users: int  # Users without WhatsApp (email only)
    # Subscription health
    expired_subscriptions: int  # Pro with expired dates
    expiring_soon: int  # Expiring within 7 days


@router.get("/metrics/growth", response_model=GrowthMetrics)
def get_growth_metrics(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """Get business growth metrics — MRR, churn, activation funnel, trends."""
    from app.models.models import Invoice

    log_audit_event("admin.metrics.growth", user_id=admin_user.id)

    now = dt.datetime.now(dt.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    # ── MRR ──
    # Pro is prepaid (₦2,000 Pro Pack / ₦1,500 Features pass), not recurring.
    # Approximate active-Pro revenue using the Pro Pack price.
    PLAN_PRICES = {"pro": 2000}
    active_pro = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.PRO,
        (models.User.subscription_expires_at.is_(None)) |
        (models.User.subscription_expires_at >= now)
    ).count()
    mrr = active_pro * PLAN_PRICES["pro"]
    arr = mrr * 12

    # ── MRR Trend (last 6 months from payment transactions) ──
    mrr_trend: list[MonthlyDataPoint] = []
    for i in range(5, -1, -1):
        m_start = (month_start - dt.timedelta(days=1)).replace(day=1)
        for _ in range(i):
            m_start = (m_start - dt.timedelta(days=1)).replace(day=1)
        if i == 0:
            m_start = month_start
        m_end = (m_start + dt.timedelta(days=32)).replace(day=1)

        month_revenue = db.query(func.sum(PaymentTransaction.amount)).filter(
            PaymentTransaction.status == PaymentStatus.SUCCESS,
            PaymentTransaction.created_at >= m_start,
            PaymentTransaction.created_at < m_end,
        ).scalar() or 0

        mrr_trend.append(MonthlyDataPoint(
            month=m_start.strftime("%Y-%m"),
            value=float(month_revenue) / 100 if month_revenue > 1000 else float(month_revenue)
        ))

    # ── Churn ──
    # Users on paid plans whose subscription expired and didn't renew
    churned = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.PRO,
        models.User.subscription_expires_at.isnot(None),
        models.User.subscription_expires_at < now,
    ).count()

    total_paid = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.PRO
    ).count()
    churn_rate = (churned / total_paid * 100) if total_paid > 0 else 0

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

    # Users who upgraded to a paid plan
    upgraded = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.PRO
    ).count()

    funnel = ActivationFunnel(
        total_signups=total_signups,
        created_first_invoice=users_with_invoice,
        received_first_payment=users_with_payment,
        upgraded_to_paid=upgraded,
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
    revenue_growth: list[MonthlyDataPoint] = []

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
        revenue_growth.append(MonthlyDataPoint(month=label, value=float(month_rev)))

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

    # ── Subscription Health ──
    expired = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.PRO,
        models.User.subscription_expires_at.isnot(None),
        models.User.subscription_expires_at < now,
    ).count()

    seven_days = now + dt.timedelta(days=7)
    expiring = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.PRO,
        models.User.subscription_expires_at.isnot(None),
        models.User.subscription_expires_at >= now,
        models.User.subscription_expires_at <= seven_days,
    ).count()

    return GrowthMetrics(
        mrr=mrr,
        mrr_trend=mrr_trend,
        arr=arr,
        churned_users=churned,
        churn_rate=round(churn_rate, 1),
        activation_funnel=funnel,
        collection_rate=round(collection_rate, 1),
        avg_days_to_payment=avg_days_to_payment,
        user_growth=user_growth,
        invoice_growth=invoice_growth,
        revenue_growth=revenue_growth,
        avg_invoices_per_user=avg_invoices_per_user,
        power_users=power_users,
        zero_invoice_users=zero_invoice,
        whatsapp_users=whatsapp_users,
        email_only_users=email_only_users,
        expired_subscriptions=expired,
        expiring_soon=expiring,
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

