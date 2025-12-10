"""
Expense tracking API endpoints.

Handles CRUD operations for business expenses and provides summary/stats endpoints.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.api.dependencies import get_data_owner_id
from app.db.session import get_db
from app.models.expense import Expense
from app.models.expense_schemas import (
    ExpenseCreate,
    ExpenseOut,
    ExpenseStats,
    ExpenseSummary,
    ExpenseUpdate,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])

# Type aliases for dependency injection
CurrentUserDep = Annotated[int, Depends(get_current_user_id)]
DataOwnerDep = Annotated[int, Depends(get_data_owner_id)]
DbDep = Annotated[Session, Depends(get_db)]


def _calculate_period_range(
    period_type: str,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    week: int | None = None,
) -> tuple[date, date]:
    """
    Calculate start and end date for a given period.
    
    Same logic as tax reporting for consistency.
    """
    today = date.today()
    
    if period_type == "day":
        if year and month and day:
            target_date = date(year, month, day)
        else:
            target_date = today
        return target_date, target_date
    
    elif period_type == "week":
        if year and week:
            # ISO week calculation
            jan4 = date(year, 1, 4)
            week_one_start = jan4 - timedelta(days=jan4.isoweekday() - 1)
            target_start = week_one_start + timedelta(weeks=week - 1)
            target_end = target_start + timedelta(days=6)
        else:
            # Current week
            target_start = today - timedelta(days=today.isoweekday() - 1)
            target_end = target_start + timedelta(days=6)
        return target_start, target_end
    
    elif period_type == "month":
        if year and month:
            target_year, target_month = year, month
        else:
            target_year, target_month = today.year, today.month
        
        start_date = date(target_year, target_month, 1)
        # Last day of month
        if target_month == 12:
            end_date = date(target_year, 12, 31)
        else:
            end_date = date(target_year, target_month + 1, 1) - timedelta(days=1)
        return start_date, end_date
    
    elif period_type == "year":
        target_year = year if year else today.year
        return date(target_year, 1, 1), date(target_year, 12, 31)
    
    else:
        raise ValueError(f"Invalid period_type: {period_type}")


@router.post("/", response_model=ExpenseOut, status_code=201)
def create_expense(
    data: ExpenseCreate,
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
):
    """
    Create a new expense manually from dashboard.
    
    For WhatsApp/email expenses, use the bot message handler.
    Expense is created under the data owner (team admin for members).
    """
    expense = Expense(
        user_id=data_owner_id,
        amount=data.amount,
        date=data.expense_date,
        category=data.category,
        description=data.description,
        merchant=data.merchant,
        notes=data.notes,
        input_method="manual",
        channel="dashboard",
        verified=True,  # Manual entries are auto-verified
    )
    
    db.add(expense)
    db.commit()
    db.refresh(expense)
    
    return expense


@router.get("/", response_model=list[ExpenseOut])
def list_expenses(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
    start_date: date | None = Query(None, description="Filter by start date (inclusive)"),
    end_date: date | None = Query(None, description="Filter by end date (inclusive)"),
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(100, ge=1, le=500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    List expenses with optional filters.
    
    Returns expenses sorted by date (most recent first).
    For team members, returns the team admin's expenses.
    """
    q = db.query(Expense).filter(Expense.user_id == data_owner_id)
    
    if start_date:
        q = q.filter(Expense.date >= start_date)
    if end_date:
        q = q.filter(Expense.date <= end_date)
    if category:
        q = q.filter(Expense.category == category)
    
    q = q.order_by(Expense.date.desc(), Expense.created_at.desc())
    q = q.limit(limit).offset(offset)
    
    return q.all()


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: int,
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
):
    """Get a specific expense by ID"""
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == data_owner_id,
    ).first()
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    return expense


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    data: ExpenseUpdate,
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
):
    """Update an existing expense"""
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == data_owner_id,
    ).first()
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(expense, field, value)
    
    expense.updated_at = datetime.now()
    
    db.commit()
    db.refresh(expense)
    
    return expense


@router.delete("/{expense_id}", status_code=204)
def delete_expense(
    expense_id: int,
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
):
    """Delete an expense"""
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == data_owner_id,
    ).first()
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    db.delete(expense)
    db.commit()
    
    return None


@router.get("/summary/by-period", response_model=ExpenseSummary)
def expense_summary(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
    period_type: str = Query("month", pattern="^(day|week|month|year)$"),
    year: int | None = Query(None, description="Year (required for week/month/year)"),
    month: int | None = Query(None, ge=1, le=12, description="Month (1-12, for month period)"),
    day: int | None = Query(None, ge=1, le=31, description="Day (for day period)"),
    week: int | None = Query(None, ge=1, le=53, description="ISO week number (for week period)"),
):
    """
    Get expense summary by category for a given period.
    
    Examples:
    - Daily: /summary/by-period?period_type=day&year=2025&month=11&day=10
    - Weekly: /summary/by-period?period_type=week&year=2025&week=45
    - Monthly: /summary/by-period?period_type=month&year=2025&month=11
    - Yearly: /summary/by-period?period_type=year&year=2025
    - Current month: /summary/by-period?period_type=month
    """
    # Calculate date range
    start_date, end_date = _calculate_period_range(period_type, year, month, day, week)
    
    # Query expenses in period (use data_owner_id for team context)
    expenses = db.query(Expense).filter(
        Expense.user_id == data_owner_id,
        Expense.date >= start_date,
        Expense.date <= end_date,
    ).all()
    
    # Aggregate by category
    by_category: dict[str, Decimal] = {}
    total = Decimal("0")
    
    for expense in expenses:
        category = expense.category
        by_category[category] = by_category.get(category, Decimal("0")) + expense.amount
        total += expense.amount
    
    return ExpenseSummary(
        total_expenses=float(total),
        by_category={k: float(v) for k, v in by_category.items()},
        period_type=period_type,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        count=len(expenses),
    )


@router.get("/stats/overview", response_model=ExpenseStats)
def expense_stats(
    current_user_id: CurrentUserDep,
    data_owner_id: DataOwnerDep,
    db: DbDep,
    period_type: str = Query("month", pattern="^(day|week|month|year)$"),
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    day: int | None = Query(None, ge=1, le=31),
    week: int | None = Query(None, ge=1, le=53),
):
    """
    Get comprehensive expense statistics including revenue and profit.
    
    Shows:
    - Total expenses
    - Total revenue (from invoices)
    - Actual profit (revenue - expenses)
    - Expense-to-revenue ratio
    - Top expense categories
    """
    from app.services.tax_reporting_service import compute_revenue_by_date_range
    
    # Calculate date range
    start_date, end_date = _calculate_period_range(period_type, year, month, day, week)
    
    # Get expenses (use data_owner_id for team context)
    expenses = db.query(Expense).filter(
        Expense.user_id == data_owner_id,
        Expense.date >= start_date,
        Expense.date <= end_date,
    ).all()
    
    # Calculate totals
    total_expenses = sum(expense.amount for expense in expenses)
    
    # Get revenue from invoices (use data_owner_id for team context)
    total_revenue = compute_revenue_by_date_range(
        db=db,
        user_id=data_owner_id,
        start_date=start_date,
        end_date=end_date,
        basis="paid",  # Use paid basis for actual cash flow
    )
    
    # Calculate profit
    actual_profit = total_revenue - total_expenses
    
    # Calculate expense-to-revenue ratio
    if total_revenue > 0:
        expense_ratio = float(total_expenses / total_revenue * 100)
    else:
        expense_ratio = 0.0
    
    # Get top categories
    category_totals: dict[str, Decimal] = {}
    for expense in expenses:
        cat = expense.category
        category_totals[cat] = category_totals.get(cat, Decimal("0")) + expense.amount
    
    # Sort and get top 5
    top_categories = [
        {cat: float(amt)}
        for cat, amt in sorted(
            category_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
    ]
    
    return ExpenseStats(
        total_expenses=float(total_expenses),
        total_revenue=float(total_revenue),
        actual_profit=float(actual_profit),
        expense_to_revenue_ratio=round(expense_ratio, 2),
        top_categories=top_categories,
        period_type=period_type,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
