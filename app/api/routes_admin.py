import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query
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

router = APIRouter(prefix="/admin", tags=["admin"])


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
async def admin_root(admin_user=Depends(get_current_admin)) -> dict:
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
async def get_user_stats(
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
    
    # Total users
    total = db.query(models.User).count()
    
    # Verified vs unverified
    verified = db.query(models.User).filter(models.User.phone_verified.is_(True)).count()
    
    # Users by plan
    plan_counts = db.query(
        models.User.plan,
        func.count(models.User.id)
    ).group_by(models.User.plan).all()
    
    users_by_plan = {str(plan.value): count for plan, count in plan_counts}
    
    # Registration stats
    registered_today = db.query(models.User).filter(
        models.User.created_at >= today_start
    ).count()
    
    registered_this_week = db.query(models.User).filter(
        models.User.created_at >= week_start
    ).count()
    
    registered_this_month = db.query(models.User).filter(
        models.User.created_at >= month_start
    ).count()
    
    # Active users (logged in last 30 days)
    active_last_30_days = db.query(models.User).filter(
        models.User.last_login >= thirty_days_ago
    ).count()
    
    return UserStats(
        total_users=total,
        verified_users=verified,
        unverified_users=total - verified,
        users_by_plan=users_by_plan,
        users_registered_today=registered_today,
        users_registered_this_week=registered_this_week,
        users_registered_this_month=registered_this_month,
        active_users_last_30_days=active_last_30_days
    )


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    plan: str | None = Query(None, description="Filter by plan (free, starter, pro, business)"),
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
            role=user.role
        )
        for user in users
    ]


@router.get("/users/{user_id}", response_model=UserDetailOut)
async def get_user_detail(
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
        return {"error": "User not found"}
    
    # Count invoices
    total_invoices = db.query(models.Invoice).filter(
        models.Invoice.issuer_id == user_id
    ).count()
    
    revenue_invoices = db.query(models.Invoice).filter(
        models.Invoice.issuer_id == user_id,
        models.Invoice.invoice_type == "revenue"
    ).count()
    
    expense_invoices = db.query(models.Invoice).filter(
        models.Invoice.issuer_id == user_id,
        models.Invoice.invoice_type == "expense"
    ).count()
    
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
    # For new users with 5 free invoices, total would be total_invoices + remaining balance - 5
    # Simpler: invoices_used = total_invoices (each invoice created consumes 1)
    invoices_used = total_invoices
    
    # Build pack purchase history
    pack_purchases = []
    for purchase in invoice_pack_purchases:
        pack_purchases.append({
            "reference": purchase.reference,
            "amount": purchase.amount / 100,  # Convert kobo to naira
            "invoices_added": 100,  # Standard pack size
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
            role=user.role
        ),
        "activity": {
            "total_invoices": total_invoices,
            "revenue_invoices": revenue_invoices,
            "expense_invoices": expense_invoices,
            "total_customers": total_customers,
            "has_logo": user.logo_url is not None,
            "has_bank_details": user.account_number is not None,
            "invoice_balance": invoice_balance,
            "invoices_used": invoices_used,
            "pack_purchases": pack_purchases
        }
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
    total_commission_earned: int  # Total commission from all paid referrals (₦500 each)
    pending_payout_amount: int  # Sum of pending rewards to be paid out
    users_with_payout_bank: int  # Number of users who have set up payout bank


@router.get("/referrals/stats", response_model=ReferralStats)
async def get_referral_stats(
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
        desc("referral_count")
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
                "commission_earned": (paid_count or 0) * REFERRAL_COMMISSION_AMOUNT,
                "payout_bank_name": user.payout_bank_name
            })
    
    # Commission/Payout stats
    total_commission_earned = paid * REFERRAL_COMMISSION_AMOUNT  # ₦500 per paid referral
    
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
    phone: str
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
async def get_referral_payouts(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
    month: int | None = Query(None, description="Month (1-12), defaults to current"),
    year: int | None = Query(None, description="Year, defaults to current"),
) -> Any:
    """
    Get list of all users with pending referral commission payouts.
    
    Shows all users who have referred Pro subscribers and are owed commission.
    Use month/year to filter to a specific period (for monthly payouts).
    
    Returns bank account details for each user so you can process payments.
    """
    from app.models.referral_models import (
        Referral,
        ReferralStatus,
        ReferralType,
        REFERRAL_COMMISSION_AMOUNT,
    )
    
    log_audit_event("admin.referrals.payouts", user_id=admin_user.id, month=month, year=year)
    
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
    
    # Get all users with paid referrals in the period
    paid_referrals_query = db.query(
        Referral.referrer_id,
        func.count(Referral.id).label("paid_count")
    ).filter(
        Referral.status == ReferralStatus.COMPLETED,
        Referral.referral_type == ReferralType.PAID_SIGNUP,
        Referral.created_at >= start_date,
        Referral.created_at < end_date
    ).group_by(Referral.referrer_id).all()
    
    payouts = []
    total_amount = 0
    users_with_bank = 0
    users_without_bank = 0
    
    for referrer_id, paid_count in paid_referrals_query:
        user = db.query(models.User).filter(models.User.id == referrer_id).first()
        if user and paid_count > 0:
            commission = paid_count * REFERRAL_COMMISSION_AMOUNT
            has_bank = bool(user.payout_bank_name and user.payout_account_number)
            
            payouts.append(PayoutUserInfo(
                user_id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                payout_bank_name=user.payout_bank_name,
                payout_account_number=user.payout_account_number,
                payout_account_name=user.payout_account_name,
                paid_referrals=paid_count,
                commission_amount=commission,
                has_bank_details=has_bank
            ))
            
            total_amount += commission
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


@router.get("/metrics", response_model=PlatformMetrics)
async def get_platform_metrics(
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
    
    # Get paying users (Starter and Pro - BUSINESS removed)
    paid_plans = [SubscriptionPlan.STARTER, SubscriptionPlan.PRO]
    paid_users_query = db.query(models.User).filter(
        models.User.plan.in_(paid_plans)
    ).order_by(desc(models.User.subscription_started_at)).all()
    
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
        paid_users=paid_users_list
    )


# =============================================================================
# USER SEGMENTS FOR CAMPAIGNS (Brevo Email/WhatsApp Export)
# =============================================================================

class UserSegmentExport(BaseModel):
    """User data formatted for Brevo campaign import."""
    name: str
    phone: str
    email: str | None
    plan: str
    invoice_balance: int
    total_invoices: int
    days_since_signup: int
    days_since_last_login: int | None
    business_name: str | None


@router.get("/users/segments/inactive", response_model=list[UserSegmentExport])
async def get_inactive_users(
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
    users_with_invoices = db.query(models.Invoice.user_id).distinct().subquery()
    
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
async def get_low_balance_users(
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
            models.Invoice.user_id == user.id
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
async def get_active_free_users(
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
        models.Invoice.user_id,
        func.count(models.Invoice.id).label('invoice_count')
    ).group_by(models.Invoice.user_id).having(
        func.count(models.Invoice.id) >= min_invoices
    ).subquery()
    
    active_free_users = db.query(models.User, user_invoice_counts.c.invoice_count).join(
        user_invoice_counts,
        models.User.id == user_invoice_counts.c.user_id
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
async def get_churned_users(
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
    users_with_invoices = db.query(models.Invoice.user_id).distinct().subquery()
    
    churned_users = db.query(models.User).filter(
        models.User.id.in_(db.query(users_with_invoices)),
        models.User.last_login < cutoff
    ).all()
    
    result = []
    for user in churned_users:
        invoice_count = db.query(func.count(models.Invoice.id)).filter(
            models.Invoice.user_id == user.id
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
async def get_starter_users(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin),
) -> list[UserSegmentExport]:
    """
    Get STARTER plan users (bought invoice packs).
    Perfect for Pro upsell campaign - "Unlock analytics, inventory, team management"
    """
    log_audit_event("admin.segments.starter", user_id=admin_user.id)
    
    now = dt.datetime.now(dt.timezone.utc)
    
    starter_users = db.query(models.User).filter(
        models.User.plan == SubscriptionPlan.STARTER
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
async def get_pro_users(
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
    
    # Get users based on segment
    now = dt.datetime.now(dt.timezone.utc)
    users = []
    
    if segment == "inactive":
        # Users who never created an invoice
        users_with_invoices = db.query(models.Invoice.issuer_id).distinct()
        users = db.query(models.User).filter(
            ~models.User.id.in_(users_with_invoices)
        ).all()
    
    elif segment == "low-balance":
        # FREE users with low invoice balance
        users = db.query(models.User).filter(
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
        
        users = db.query(models.User).filter(
            models.User.id.in_(
                db.query(user_invoice_counts.c.issuer_id)
            ),
            models.User.plan == SubscriptionPlan.FREE
        ).all()
    
    elif segment == "churned":
        # Users inactive for 14+ days
        cutoff = now - dt.timedelta(days=14)
        users_with_invoices = db.query(models.Invoice.issuer_id).distinct()
        users = db.query(models.User).filter(
            models.User.id.in_(users_with_invoices),
            models.User.last_login < cutoff
        ).all()
    
    elif segment == "starter":
        # STARTER plan users (bought invoice packs) - for Pro upsell
        users = db.query(models.User).filter(
            models.User.plan == SubscriptionPlan.STARTER
        ).all()
    
    elif segment == "pro":
        # PRO plan users (monthly subscribers) - for retention
        users = db.query(models.User).filter(
            models.User.plan == SubscriptionPlan.PRO
        ).all()
    
    elif segment == "all":
        # ALL users - sync entire user base to Brevo
        users = db.query(models.User).all()
    
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
async def export_users_csv(
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
    
    users = db.query(models.User).all()
    
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
