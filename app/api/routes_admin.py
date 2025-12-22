from fastapi import APIRouter, Depends, Query
from app.core.cache import cached
from app.api.routes_admin_auth import get_current_admin
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.db.session import get_db
from app.models import models
from app.models.models import SubscriptionPlan
from app.core.audit import log_audit_event
from pydantic import BaseModel
import datetime as dt
from typing import Any

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/")
async def admin_root(admin_user=Depends(get_current_admin)) -> dict:
    """
    Admin API root - lists available endpoints.
    """
    return {
        "message": "Admin API",
        "endpoints": {
            "GET /admin/users/count": "Get total user count (cached)",
            "GET /admin/users/stats": "Get comprehensive user statistics",
            "GET /admin/users": "List all users with filtering (query params: skip, limit, plan, verified_only, search)",
            "GET /admin/users/{user_id}": "Get detailed user information including activity"
        },
        "authenticated_as": {
            "id": admin_user.id,
            "name": admin_user.name,
            "email": admin_user.email,
            "role": admin_user.role
        }
    }


class UserListItem(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str
    plan: str
    phone_verified: bool
    created_at: dt.datetime
    last_login: dt.datetime | None
    invoices_this_month: int
    business_name: str | None
    role: str

    class Config:
        from_attributes = True


class UserStats(BaseModel):
    total_users: int
    verified_users: int
    unverified_users: int
    users_by_plan: dict[str, int]
    users_registered_today: int
    users_registered_this_week: int
    users_registered_this_month: int
    active_users_last_30_days: int


@router.get("/users/count")
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
    verified = db.query(models.User).filter(models.User.phone_verified == True).count()
    
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
        query = query.filter(models.User.phone_verified == True)
    
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


@router.get("/users/{user_id}", response_model=dict)
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
    
    # Count customers
    total_customers = db.query(models.Customer).filter(
        models.Customer.user_id == user_id
    ).count()
    
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
            "has_bank_details": user.account_number is not None
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


@router.get("/referrals/stats", response_model=ReferralStats)
async def get_referral_stats(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_admin)
) -> Any:
    """Get comprehensive referral program statistics."""
    from app.models.referral_models import (
        ReferralCode, Referral, ReferralReward,
        ReferralStatus, ReferralType, RewardStatus
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
    
    # Top referrers
    top_referrers_query = db.query(
        Referral.referrer_id,
        func.count(Referral.id).label("referral_count")
    ).filter(
        Referral.status == ReferralStatus.COMPLETED
    ).group_by(Referral.referrer_id).order_by(
        desc("referral_count")
    ).limit(10).all()
    
    top_referrers = []
    for referrer_id, count in top_referrers_query:
        user = db.query(models.User).filter(models.User.id == referrer_id).first()
        if user:
            top_referrers.append({
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "referral_count": count
            })
    
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
        referrals_this_month=referrals_month
    )


# ============================================================================
# Platform Metrics
# ============================================================================

class PaidUserInfo(BaseModel):
    """Info about a paid user including referral status."""
    id: int
    name: str
    email: str | None
    phone: str
    plan: str
    business_name: str | None
    created_at: dt.datetime
    subscription_started_at: dt.datetime | None
    subscription_expires_at: dt.datetime | None
    was_referred: bool
    referred_by_name: str | None = None
    referred_by_id: int | None = None

    class Config:
        from_attributes = True


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
    from app.models.models import Invoice, Customer
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
    
    # Get paid users (Basic, Pro, Business - not free or starter)
    paid_plans = [SubscriptionPlan.BASIC, SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS]
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
