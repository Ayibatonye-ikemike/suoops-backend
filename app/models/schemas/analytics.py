"""Analytics-related schemas."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class RevenueMetrics(BaseModel):
    """Revenue breakdown and growth metrics."""
    total_revenue: float
    paid_revenue: float
    pending_revenue: float
    overdue_revenue: float
    growth_rate: float  # Percentage change from previous period
    average_invoice_value: float


class InvoiceMetrics(BaseModel):
    """Invoice counts and conversion metrics."""
    total_invoices: int
    paid_invoices: int
    pending_invoices: int
    awaiting_confirmation: int
    cancelled_invoices: int
    conversion_rate: float  # Percentage of paid invoices


class CustomerMetrics(BaseModel):
    """Customer engagement metrics."""
    total_customers: int
    active_customers: int  # Customers with invoices in period
    new_customers: int
    repeat_customer_rate: float  # Percentage with multiple invoices


class AgingReport(BaseModel):
    """Accounts receivable aging buckets."""
    current: float  # 0-30 days
    days_31_60: float
    days_61_90: float
    over_90_days: float
    total_outstanding: float


class MonthlyTrend(BaseModel):
    """Monthly revenue, expenses, and profit trend."""
    month: str  # "Jan 2025"
    revenue: float
    expenses: float
    profit: float
    invoice_count: int


class AnalyticsDashboard(BaseModel):
    """Complete analytics dashboard data."""
    period: str
    currency: str
    start_date: dt.date
    end_date: dt.date
    revenue: RevenueMetrics
    invoices: InvoiceMetrics
    customers: CustomerMetrics
    aging: AgingReport
    monthly_trends: list[MonthlyTrend]
