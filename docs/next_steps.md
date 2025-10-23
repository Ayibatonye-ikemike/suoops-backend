# Next Steps (Actionable Backlog Slice)

## High Priority (Start Now)
1. Implement Prometheus metrics exporter & wire existing facade.
2. Document Paystack incident response (signature rotation, webhook replay procedures).
3. Add idempotency persistence table (webhook_events) with unique(event_id, source_provider).
4. Introduce Redis and refactor WhatsApp handler to enqueue processing jobs.
5. Add receipt generation endpoint (re-using PDF pipeline; template + test).

## Medium Priority
6. Structured logging (JSON) with request + correlation IDs.
7. Add OpenAPI tags descriptions + examples for all endpoints.
8. Expand tests: edge cases (0 line items invoice, large discount, invalid payment ref).
9. Currency util: central quantize & rounding strategy with tests.
10. Pre-flight health endpoints: /health/ready, /health/live.

## Low Priority / Strategic
11. Outbox pattern for domain events.
12. Field-level encryption spike (PII columns mapping).
13. NLP model upgrade evaluation (fine-tuned lightweight transformer) vs rule expansion cost.
14. Multi-tenant performance benchmark (10K invoices listing).
15. Cost dashboard script (provider fees, infra estimates).

## Quick Wins (<2h)
- Add CODEOWNERS (docs + services separation).
- Add Makefile or invoke tasks for common dev flows (migrate, test, lint, run).
- Add .env.test for CI config isolation.

## Deferred / Requires Input
- OCR pipeline for paper receipts (needs sample images dataset).
- QR verification spec (needs branding + trust model decision).

## Definition of Ready (For each work item)
- Clear acceptance criteria
- Test strategy noted (unit/integration)
- Rollback / failure mode considered
- Owner assigned

## Engineering Principles Reminders
- Extract after pain, not before (measure coupling metrics)
- Instrument first, optimize second
- Prefer explicit domain events over hidden side effects
- Keep files <400 LOC (enforce in CI script upcoming)

