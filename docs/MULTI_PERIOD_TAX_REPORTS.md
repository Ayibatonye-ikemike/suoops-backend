# Multi-Period Tax Report Aggregation

## Overview
Enhanced the tax reporting system to support multiple time aggregations (day, week, month, year) instead of monthly-only reports.

## Changes Made

### Backend Changes

#### 1. Database Migration
**File**: `alembic/versions/add_period_type_to_tax_reports.py`
- Added `period_type` column (enum: day, week, month, year)
- Added `start_date` and `end_date` columns for precise period boundaries
- Made `year` and `month` nullable for non-monthly reports
- Populated existing monthly reports with calculated date ranges
- Added index on `(user_id, period_type, start_date, end_date)` for performance

#### 2. Database Model
**File**: `app/models/tax_models.py`
- Updated `MonthlyTaxReport` model with new fields
- Added `period_type`, `start_date`, `end_date` columns
- Made `year` and `month` nullable for backward compatibility
- Updated docstring to reflect multi-period support

#### 3. Tax Reporting Service
**File**: `app/services/tax_reporting_service.py`
- Added `_calculate_period_range()` method for date range calculation
  - Day: specific date (year, month, day)
  - Week: ISO 8601 week calculation (year, week number)
  - Month: first to last day of month (year, month)
  - Year: Jan 1 to Dec 31 (year)
- Added `generate_report()` method for all period types
- Added `compute_assessable_profit_by_date_range()` for flexible date queries
- Refactored `generate_monthly_report()` to delegate to `generate_report()`
- Maintains backward compatibility

#### 4. API Endpoints
**File**: `app/api/routes_tax.py`

**Updated POST /tax/reports/generate**
- Added `period_type` parameter (day/week/month/year, default: month)
- Added optional `day` parameter (for daily reports)
- Added optional `week` parameter (for weekly reports, ISO week number)
- Made `month` optional (required only for month/day reports)
- Returns `period_label` for display
- Returns `start_date` and `end_date` for reference
- Backward compatible with existing monthly report calls

**Added GET /tax/reports/{report_id}/download**
- New endpoint to download reports by ID
- Returns PDF URL and period information

**Updated GET /tax/reports/{year}/{month}/download**
- Maintained for backward compatibility
- Now filters by `period_type='month'`

**Updated CSV Endpoints**
- Added `/tax/reports/{report_id}/csv` for CSV export by ID
- Updated `/tax/reports/{year}/{month}/csv` for backward compatibility
- CSV includes all new period fields

### Frontend Changes

#### Tax Page UI
**File**: `app/(dashboard)/dashboard/tax/page.tsx`

**New Features**:
- Period type selector dropdown (Daily/Weekly/Monthly/Yearly)
- Conditional date pickers based on selected period:
  - **Daily**: Year + Month + Day selectors
  - **Weekly**: Year + ISO Week number selector (1-53)
  - **Monthly**: Year + Month selectors (default)
  - **Yearly**: Year selector only
- Updated report header to display `period_label` from backend
- Updated API calls to pass appropriate parameters based on period type
- Updated download to use new report ID endpoint

**Interface Updates**:
- Extended `MonthlyReport` interface with:
  - `id`: Report ID for downloads
  - `period_type`: Selected period type
  - `period_label`: Formatted period label (e.g., "2025-01-15", "2025-W03", "2025-01", "2025")
  - `start_date` and `end_date`: Period boundaries
  - Made `month` nullable for non-monthly reports

## API Examples

### Daily Report
```bash
POST /tax/reports/generate?period_type=day&year=2025&month=1&day=15&basis=paid
```

### Weekly Report
```bash
POST /tax/reports/generate?period_type=week&year=2025&week=3&basis=paid
```

### Monthly Report (Default)
```bash
POST /tax/reports/generate?year=2025&month=1&basis=paid
# OR explicitly:
POST /tax/reports/generate?period_type=month&year=2025&month=1&basis=paid
```

### Yearly Report
```bash
POST /tax/reports/generate?period_type=year&year=2025&basis=paid
```

### Download Report
```bash
# By report ID (new)
GET /tax/reports/{report_id}/download

# By year/month (backward compatible, monthly only)
GET /tax/reports/2025/1/download
```

## Response Format

```json
{
  "id": 123,
  "period_type": "week",
  "period_label": "2025-W03",
  "start_date": "2025-01-13",
  "end_date": "2025-01-19",
  "year": 2025,
  "month": null,
  "assessable_profit": 50000.00,
  "levy_amount": 2000.00,
  "vat_collected": 3750.00,
  "taxable_sales": 50000.00,
  "zero_rated_sales": 0.00,
  "exempt_sales": 0.00,
  "pdf_url": "https://...",
  "basis": "paid"
}
```

## Database Schema

### Before (Monthly Only)
```sql
CREATE TABLE monthly_tax_reports (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    assessable_profit NUMERIC(15, 2),
    ...
);
```

### After (Multi-Period)
```sql
CREATE TABLE monthly_tax_reports (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    period_type VARCHAR(10) DEFAULT 'month',  -- NEW
    start_date DATE,                          -- NEW
    end_date DATE,                            -- NEW
    year INTEGER,                             -- Now nullable
    month INTEGER,                            -- Now nullable
    assessable_profit NUMERIC(15, 2),
    ...
);

CREATE INDEX ix_tax_reports_period_dates 
ON monthly_tax_reports(user_id, period_type, start_date, end_date);
```

## Backward Compatibility

All existing functionality is preserved:
1. Monthly reports remain the default (`period_type='month'`)
2. Existing API calls without `period_type` work as before
3. Legacy `/tax/reports/{year}/{month}/download` endpoint still functions
4. Existing database records automatically updated with `period_type='month'` and calculated dates
5. `year` and `month` columns retained for backward compatibility

## Migration Path

1. **Run migration**: `alembic upgrade head`
2. **Deploy backend**: New API supports all period types
3. **Deploy frontend**: UI shows period selector
4. **Existing reports**: Automatically tagged as `period_type='month'` with calculated dates

## Testing Checklist

- [ ] Run database migration on development
- [ ] Test daily report generation
- [ ] Test weekly report generation (ISO week numbers)
- [ ] Test monthly report generation (existing functionality)
- [ ] Test yearly report generation
- [ ] Verify backward compatibility with existing monthly reports
- [ ] Test PDF downloads for all period types
- [ ] Test CSV exports for all period types
- [ ] Verify UI period selector works correctly
- [ ] Check edge cases: week 53, leap years, month boundaries

## Next Steps

1. Run migration in staging environment
2. Test all period types with real data
3. Deploy to production
4. Monitor for any issues
5. Consider adding:
   - Quarterly reports
   - Custom date ranges
   - Report comparison across periods
   - Trend analysis

## Commits

**Backend**: `780e2e91` - feat: add multi-period aggregation to tax reports (day/week/month/year)
**Frontend**: `33e11e0` - feat: add multi-period aggregation UI to tax reports
