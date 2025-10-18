# Prioritized Backlog (Epics & Stories)

Legend: MUST = MVP core, SHOULD = near-term enhancer (still MVP window if capacity), LATER = post-MVP.

## Epic: Auth & Identity
MUST:
- Register user (phone, name, password/JWT) – done.
- Derive issuer from JWT in invoice creation (remove issuer_id parameter).
SHOULD:
- Password reset via OTP (stub service).
LATER:
- Multi-user org roles (owner, agent).

## Epic: WhatsApp Interaction
MUST:
- Inbound webhook route & minimal validation.
- NLP parse invoice command (name, amount, due date phrase like "tomorrow").
SHOULD:
- EDIT / YES confirmation loop for user corrections.
- Basic help command (HELP returns syntax examples).
LATER:
- Voice note transcription integration.
- Template message sending (approved Meta templates) for reminders.

## Epic: NLP Parsing
MUST:
- Rule-based extraction (customer name, amount, due_date simple phrases).
SHOULD:
- Multi-line item parsing pattern: `<qty>x <desc> @ <price>`.
- Natural date phrases ("in 3 days", "next week Monday").
LATER:
- Model-based intent classification fallback.
- Confidence scoring & user clarification prompts.

## Epic: Invoicing Core
MUST:
- Create invoice with single/line items.
- Generate PDF with QR (later milestone) & store link.
- Status transitions: pending -> paid -> overdue.
SHOULD:
- Manual mark as paid (offline payment) with audit entry.
- Discounts / simple tax field (percentage & amount).
LATER:
- Partial payments (installments) ledger.
- Credit notes & reversals.

## Epic: Payments
MUST:
- Paystack create link + webhook verify.
SHOULD:
- Flutterwave provider fallback with provider selection strategy.
- Reconciliation job to poll unmatched pending invoices.
LATER:
- Bulk payout (Phase 2) integration.
- Provider failover mid-transaction metrics.

## Epic: PDF Generation
MUST:
- ReportLab or HTML->PDF baseline invoice & payslip.
SHOULD:
- Themed Jinja template (branding placeholders: logo, color primary).
- QR embed linking to verification endpoint.
LATER:
- Template marketplace (select style by template_id).
- Right-to-left / localization support.

## Epic: Notifications
MUST:
- Log events (invoice_created, invoice_paid) to notification service stub.
SHOULD:
- WhatsApp sending abstraction (queued) with retry strategy.
- Overdue reminders job (daily / hourly pass).
LATER:
- Email fallback + SMS fallback.
- Notification preference center per user.

## Epic: Payroll
MUST:
- Worker CRUD & payroll run calculation.
- Payslip PDF generation.
SHOULD:
- Simple deductions field (flat amount per worker).
- NET vs GROSS breakdown in schema.
LATER:
- Attendance ingestion (daily ack) feeding payroll.
- Bulk payouts to workers.

## Epic: OCR / Photo to Invoice
SHOULD:
- Image upload -> parse total + vendor name.
- Confidence threshold & fallback manual confirm.
LATER:
- Line item segmentation.
- Multi-language OCR packs.

## Epic: Observability & Ops
MUST:
- Structured logging & correlation id (request id middleware).
SHOULD:
- Prometheus metrics (counters, histograms) & /metrics endpoint.
- Rate limiting (token bucket in Redis) for create invoice.
LATER:
- Distributed tracing (OTel) traces for payment lifecycle.

## Epic: Security & Compliance
MUST:
- Secure secret loading (.env + production overrides).
SHOULD:
- JWT refresh token endpoint.
- Basic PII scrubbing (logs exclude phone numbers beyond last 4 digits).
LATER:
- Encrypted at-rest fields (worker names) using KMS.

## Backlog Table Snapshot
| Epic | MUST (High Priority) | SHOULD (Medium) | LATER (Deferred) |
|------|----------------------|-----------------|------------------|
| Auth | Register/Login | Password reset | Org roles |
| WhatsApp | Webhook, parse | Edit/Help | Voice / Templates |
| NLP | Basic extract | Multi-line, dates | ML intent |
| Invoicing | Create, PDF, status | Manual paid, discounts | Partial payments |
| Payments | Paystack | Flutterwave, reconcile | Bulk payout |
| PDF | Base invoice | Branding, QR | Template marketplace |
| Notifications | Event log | WhatsApp queue, overdue | Email/SMS prefs |
| Payroll | Run calc | Deductions | Attendance, payouts |
| OCR | (none) | Total+vendor | Line items, multi-lang |
| Observability | Structured logs | Metrics, rate limit | Tracing |
| Security | Secrets mgmt | Refresh tokens, PII mask | Field encryption |

## DRY / SRP Enforcement Notes
- No business decisions in routers; they only map request → service method.
- Parsing logic centralized in `NLPService`; invoices never parse user text directly.
- Payment-specific HTTP logic isolated in `PaymentService`; invoice flow receives only an abstraction (link URL, status updates).
- Common formatting (currency, IDs) resides in `utils` to avoid duplication across services.
