# Suoops Tax Automation & Manual Flows

This document explains how automated monthly tax compliance reporting works alongside the existing manual levy calculation flow. Both paths intentionally coexist so teams can gradually adopt automation.

## Overview

| Capability | Manual Endpoint | Automated Mechanism | Output |
|------------|-----------------|---------------------|--------|
| Development Levy (ad‑hoc) | `GET /tax/levy` | Included in monthly report | JSON response / part of PDF |
| Assessable Profit (period/basis) | `GET /tax/levy?year=&month=&basis=` | Recomputed during monthly report generation | JSON / PDF |
| VAT Breakdown (month) | (aggregated internally) | Monthly report aggregation | PDF section |
| Consolidated Monthly Report | `POST /tax/reports/generate` | Celery task `tax.generate_previous_month_reports` (scheduled) | Metadata row + PDF |
| Download Report | `GET /tax/reports/{year}/{month}/download` | Same (after automation runs) | PDF URL |

## Manual Flow (On‑Demand)
Use when you want a quick levy figure or to experiment with profit basis:
```http
GET /tax/levy?year=2025&month=10&basis=paid
```
- Optional `profit` query param overrides computed assessable profit.
- Returns JSON with `levy_amount`, `assessable_profit`, `source`, and `period`.

## Automated Monthly Report
Runs once per month to consolidate:
- Assessable profit (discounts subtracted, future-due excluded)
- Development levy (4% if not small business)
- VAT collected and sales breakdown: taxable, zero-rated, exempt

### Generation (Manual Trigger)
```http
POST /tax/reports/generate?year=2025&month=10&basis=paid
```
Response contains aggregated metrics and (if created previously) `pdf_url`.

### Download PDF
```http
GET /tax/reports/2025/10/download
```
Returns `{ "pdf_url": "...signed or local URI..." }`.

## Automation Task
Celery task: `tax.generate_previous_month_reports`
- Enumerates users.
- Generates (or skips if existing) previous month report.
- Creates PDF via HTML (WeasyPrint) or ReportLab fallback.

### Scheduling (Example Crontab for Celery Beat)
Add to Celery beat config (pseudo):
```python
CELERY_BEAT_SCHEDULE = {
  "monthly-tax-reports": {
    "task": "tax.generate_previous_month_reports",
    "schedule": crontab(minute=0, hour=2, day_of_month=1),  # 02:00 UTC first day monthly
    "args": ["paid"],
  }
}
```

## Data Model
`MonthlyTaxReport` fields:
- `user_id`, `year`, `month`
- `assessable_profit`, `levy_amount`
- `vat_collected`, `taxable_sales`, `zero_rated_sales`, `exempt_sales`
- `pdf_url`, timestamps

## PDF Generation
- HTML template: `templates/monthly_tax_report.html`
- If `settings.HTML_PDF_ENABLED` and WeasyPrint available: full styled PDF.
- Else: ReportLab fallback with summary lines.
- Stored via `S3Client.upload_bytes` (presigned URL) or local filesystem fallback.

## Profit & Levy Logic Recap
Assessable profit rules:
- Basis `paid`: only invoices with status `paid`.
- Basis `all`: all non-refunded invoices.
- Excludes future-due invoices (`due_date > now`).
- Subtracts `discount_amount` when present.

Development Levy:
- 4% of assessable profit for non-small businesses.
- Small businesses: exempt (0%).

## Migration Strategy
1. Continue using `GET /tax/levy` for interactive dashboard.
2. Introduce a UI button to trigger monthly report generation if automation isn't yet scheduled.
3. Enable Celery beat scheduling in production.
4. Add alerting for failed report generation attempts (future enhancement).

## New Additions (Current Release)
- Refunded invoice handling implemented: basis `all` excludes status `refunded`; monthly report & VAT breakdown automatically exclude refunded invoices.
- CSV export endpoint: `GET /tax/reports/{year}/{month}/csv?basis=paid|all` regenerates metrics and returns a presigned CSV URL.
- Watermark feature: enable with `PDF_WATERMARK_ENABLED` / customize text via `PDF_WATERMARK_TEXT` for both invoice and monthly report PDFs (HTML + ReportLab fallback).
- Alerting: generation task records per-user failures and summary alerts in `alert_events` table (categories `tax.report` and `tax.report.summary`).

## Future Enhancements
- Include input VAT (supplier invoices) once capture is implemented.
- Add cryptographic signature & hash for PDF authenticity (beyond watermark).
- External alert forwarding (email/webhook) and dashboard surfacing of recent alerts.
- Consolidated compliance dashboard including alert counts and SLA metrics.

## Troubleshooting
| Issue | Cause | Resolution |
|-------|-------|------------|
| Missing `pdf_url` after generation | WeasyPrint failed & fallback not executed | Check logs; verify ReportLab & jinja2 installed; fallback logs warning |
| Levy shows 0 for medium business | Business classified small (thresholds) | Update turnover/assets via `/tax/profile` |
| VAT collected is 0 | Invoices missing `vat_amount` field populated | Ensure VAT calculation & persistence at invoice creation/fiscalization |
| Automation task skipped user | No invoices in period | Expected; report still generated with zeros |
| CSV export returns 404 | Report not generated yet | Call POST `/tax/reports/generate` first or ensure automation ran |
| Alerts not recorded | `alert_events` table missing migration | Run Alembic migrations up to latest revision |
| Watermark missing | Feature flag disabled | Set `PDF_WATERMARK_ENABLED=true` & optionally `PDF_WATERMARK_TEXT` |

## Security Notes
- PDFs are presigned URLs with expiry (controlled by `S3_PRESIGN_TTL`).
- Future: encrypt PDFs at rest or add watermark for internal drafts.

---
Document version: 1.0 • Generated on build commit.
