# Milestones & Exit Criteria

Each milestone aligns to isolated service responsibilities (SRP) and avoids cross-layer leakage. Implementation *must not* add business logic inside routers—keep logic in services.

## M1 – Core Invoicing Skeleton (Weeks 1–2)
Scope:
- Auth register/login (User + JWT).
- Create Invoice (single amount or 1 line item) via API.
- Stub PDF & Payment link generation.
- WhatsApp webhook stub parsing basic command.
Exit Criteria:
- POST /invoices returns invoice with pdf_url & status=pending.
- WhatsApp inbound payload with text “Invoice Jane 5000” persists an invoice.
- All new/modified files < 400 LOC (enforced by manual check script optionally).
Quality Gates:
- Unit tests: create invoice happy path, auth login, ID generation uniqueness (>= 1k sample).
- Lint + type check: PASS.

## M2 – Real Payments & Receipts (Weeks 3–4)
Scope:
- Paystack integration with signature validation.
- Update invoice on payment success; mark status=paid.
- Generate final invoice PDF (improved layout) and (optional) receipt event.
- Notification hooks logging message send (future WhatsApp send).
Exit Criteria:
- Simulated payment webhook transitions status within 5s.
- Duplicate webhook (same reference) idempotently processed (no double state change).
- Payment failure does NOT mark invoice paid.
Quality Gates:
- Webhook idempotency test passes (2 identical payloads → single status change).
- P95 create_invoice endpoint latency < 600ms local for 50 parallel requests.

## M3 – Dashboard Read + Payroll Seed (Weeks 5–6)
Scope:
- Replace `issuer_id` parameter with derived user id (auth context) for invoice creation.
- List & filter invoices endpoint.
- Introduce Worker & PayrollRun; compute gross & net (net==gross placeholder).
- Payslip PDF basic generation.
Exit Criteria:
- Invoice creation denies request without Authorization header.
- Payroll run returns accurate total_gross for at least 3 workers test case.
Quality Gates:
- Added tests: permission (unauthorized 401), payroll computation rounding.
- Coverage threshold > 40% (initial target) across services.

## M4 – Operational Hardening (Weeks 7–8)
Scope:
- Overdue job updates statuses; metrics counters.
- QR verification endpoint + QR embedding.
- Basic rate limiting (prevent spam invoice creation).
Exit Criteria:
- Overdue job marks >90% of qualifying sample invoices correctly.
- QR endpoint returns JSON with status and amount fields.
- Rate limit test (burst > threshold) returns 429.
Quality Gates:
- Load simulation (100 RPS burst 30s) no memory leak (RSS stable within 10%).
- Structured log lines appear for state transitions (INFO) & errors (ERROR).

## Stretch – OCR Draft + Multi-Line Parsing (Weeks 9–11)
Scope:
- OCR stub with at least amount extraction & vendor name.
- NLP multi-line item pattern & discount support.
Exit Criteria:
- OCR test set (>=20 samples): amount extraction ≥70% accuracy.
- Multi-line invoice totals compute correctly (rounding to 2 dp).

## Final Pilot Readiness (Week 12)
Exit Checklist:
- Security: JWT secret documented rotation, no secrets logged.
- Backup: DB logical dump script ready.
- Runbooks: payment replay, overdue manual trigger, invoice regeneration.
- Docs: API spec (v0.1), architecture diagram, backlog updated.

## Rollback Strategy
- Feature flags (env vars) for: PAYMENTS_ENABLED, OCR_ENABLED, REMINDERS_ENABLED.
- Blue/green deploy or simple canary by routing small % of WhatsApp traffic.

## Non-Goals (Explicit Defer)
- Multi-tenant org roles beyond basic issuer scoping.
- Advanced tax rules or currency conversion.
- Bulk payout automation (Phase 2).
