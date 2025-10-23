# MVP Timeline Roadmap (Weeks 1–12)

Principles: Each deliverable maps cleanly to one service or module (SRP), avoids duplicated logic (DRY), and keeps files < 400 LOC by layering domain services (`InvoiceService`, `PaymentService`, etc.).

## Week 1 – Foundations & Skeleton
Deliverables:
- FastAPI app shell (`app/api/main.py`) & base routers.
- Core config & logging (`core.config`, `core.logger`).
- DB base + session + initial Alembic migration.
- User auth models/schemas (no UI yet).
Exit Gate:
- Health endpoint responds.
- Alembic upgrade runs cleanly.

## Week 2 – Basic Invoicing Domain
Deliverables:
- `Invoice` + `InvoiceLine` models stable.
- `InvoiceService.create_invoice` happy path with stub payment + PDF.
- Rule-based `NLPService` minimal invoice parse.
- WhatsApp webhook draft route (echo / parse). 
Exit Gate:
- Manual POST or WhatsApp JSON → invoice persisted; PDF stub URL produced.

## Week 3 – Real Payment Integration (Paystack)
Deliverables:
- Paystack link creation + webhook signature verify.
- Update `InvoiceService` to persist payment_ref (if returned) & mark paid.
- Basic retry/backoff strategy (idempotent webhook handler).
Exit Gate:
- Sandbox payment marks status `paid` within <10s median.

## Week 4 – PDF Hardening & Receipt Flow
Deliverables:
- Improved PDF layout (switch to HTML/Jinja rendered then to PDF OR refine ReportLab composition module — keep under 300 LOC).
- Automatic receipt generation stub (future `Receipt` model optional) or reuse invoice with `status=paid` and deliver event.
- Notification service hooks for invoice + receipt events.
Exit Gate:
- Payment webhook triggers PDF generation exactly once (idempotent test passes).

## Week 5 – Dashboard Minimal (Read-Only)
Deliverables:
- Auth-protected endpoints (list invoices, retrieve one) with issuer scoping (replace explicit `issuer_id`).
- JWT dependency injection & removal of external issuer_id in create route.
- Basic metrics counters.
Exit Gate:
- Create invoice with Bearer token, list shows it with correct issuer filtering.

## Week 6 – Bank Details & Confirmation Flow
Deliverables:
- Bank details storage with issuer-scoped CRUD endpoints.
- Manual payment confirmation flow (bank transfer reference capture, awaiting_confirmation status).
- Settings UI section for business banking profile + plan overview.
Exit Gate:
- Invoice marked `awaiting_confirmation` transitions to `paid` once confirmation endpoint is called.

## Week 7 – Reminders & Overdue Logic
Deliverables:
- Overdue status transition job (background task scanning due_date < now & unpaid).
- Structured logging for transitions.
- Add `due_in_days` parsing phrases (NLP enrichment).
Exit Gate:
- Test set of sample invoices -> overdue classification job passes.

## Week 8 – QR Verification & Short Links
Deliverables:
- QR code embed in invoice PDF (verification URL endpoint `/invoices/{id}/verify`).
- Short verification JSON structure (status, amount, customer name fragment masked).
Exit Gate:
- Scanning QR (manually hitting URL) returns correct state for paid/pending.

## Week 9 – OCR Draft Invoices (Prototype)
Deliverables:
- `OCRService.parse_receipt` integrating Tesseract or placeholder stub returning partial fields.
- Endpoint to upload image -> returns parsed draft invoice object (not persisted until confirmed).
Exit Gate:
- At least total amount extracted for >=70% of clean sample images.

## Week 10 – Hardening & Observability
Deliverables:
- Prometheus metrics endpoint (/metrics) or custom counters.
- Structured error response format (problem JSON) middleware.
- Rate limiting (basic in-memory or Redis token bucket) for WhatsApp ingress.
Exit Gate:
- Load test 100 create requests: P95 < 500ms (local baseline) & no duplicate invoices.

## Week 11 – Multi-Line Item Parsing & Discounts
Deliverables:
- NLP pattern for `2x Wig @ 12500` → line items.
- Optional discount field (safe migration; backward compatible).
Exit Gate:
- Multi-line invoice PDF shows correct total & rounding.

## Week 12 – Pilot Readiness & Documentation
Deliverables:
- Updated API spec + postman collection.
- Runbooks: payment webhook replay, invoice recovery, overdue job manual run.
- Security checklist (JWT secret rotation steps).
Exit Gate:
- Pilot checklist signed off (auth, payments, data retention, logging).

## Post-MVP (Phase 2 & 3 Preview)
- Branded invoice themes and scheduled reminders.
- Bulk payment reconciliation dashboard.
- Microloan scoring service subscribing to invoice paid events.

## OOP / SRP Mapping Reference
| Concern | Class / Module | Rationale |
|---------|----------------|-----------|
| Invoice business rules | `InvoiceService` | Isolates domain logic from transport/webhooks |
| Payments integration | `PaymentService` | Paystack provider abstraction |
| Parsing user text | `NLPService` | Keeps rule patterns isolated & testable |
| WhatsApp transport | `WhatsAppHandler` / `WhatsAppClient` | Avoids coupling to invoice logic |
| PDF rendering | `PDFService` | Single responsibility: HTML/PDF + upload |
| Auth & tokens | `AuthService` / `core.security` | Separation of identity concerns |

All roadmap items expand these classes or add orthogonal modules—preventing any file from exceeding ~400 LOC; when growth approaches threshold, split by sub-domain (e.g., `invoice_service_payments.py`).
