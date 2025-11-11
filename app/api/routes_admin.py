from fastapi import APIRouter, Depends, Query
from app.core.cache import cached
from app.core.rbac import admin_required
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.db.session import get_db
from app.models import models
from app.models.user import SubscriptionPlan
from app.core.audit import log_audit_event
from pydantic import BaseModel
import datetime as dt
from typing import Any

router = APIRouter(prefix="/admin", tags=["admin"])


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
async def user_count(db: Session = Depends(get_db), admin_user=Depends(admin_required)) -> dict:
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
    admin_user=Depends(admin_required)
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
    admin_user=Depends(admin_required),
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
    admin_user=Depends(admin_required)
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
