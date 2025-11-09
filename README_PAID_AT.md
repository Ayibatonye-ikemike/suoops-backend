## paid_at Timestamp Semantics

`paid_at` represents the moment an invoice is manually transitioned to the `paid` status in the backend invoice workflow.

### Source of truth
The value is written inside `InvoiceService.update_status`:
1. Transition status → `paid`.
2. If previous status was not `paid` and `paid_at` is unset, set `paid_at = datetime.utcnow()` (timezone-aware UTC).
3. Generate receipt PDF (if missing) and dispatch notifications.

### Timezone
All backend timestamps are stored and emitted in UTC. Frontend formatting now uses `formatPaidAt()` which:
- Displays a concise local representation with the user’s timezone name.
- Can alternatively render an explicit UTC string (`YYYY-MM-DD HH:MM UTC`).

### When it changes
`paid_at` is immutable after the first transition to `paid` (no resets even if status changes later). This preserves auditability of payment confirmation time.

### API contract
OpenAPI schema exposes `paid_at` as `string|null` ISO8601 UTC (`2025-11-09T12:34:56.789Z`). Clients MUST treat it as read-only.

### Edge cases
- If status is toggled to `paid` then back to another status, `paid_at` remains set.
- Receipt PDF generation failures do not block setting `paid_at`.
- Bulk backfills should use the service’s public method to ensure consistent logic.

### Frontend usage
Components: public invoice page (`invoice-client.tsx`) and dashboard detail (`invoice-detail.tsx`). Both now use the shared helper.
