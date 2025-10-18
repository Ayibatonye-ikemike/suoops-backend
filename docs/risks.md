# Risk Register

| Category | Risk | Likelihood (L/M/H) | Impact (L/M/H) | Exposure | Mitigation / Preventative Controls | Trigger / Leading Indicator | Owner | Status |
|----------|------|--------------------|----------------|----------|------------------------------------|-----------------------------|-------|--------|
| Technical | Single payment provider outage (Paystack) | M | H | H | Abstract provider layer (DONE), add Flutterwave prod integration, fallback retry queue | Elevated 5xx from provider, webhook delays >5m | Eng (Payments) | Open |
| Technical | PDF generation dependency (WeasyPrint) build failures in prod container | M | M | M | Feature flag (DONE), fallback to ReportLab (DONE), pre-build layer, health check at startup | Startup log error, latency spike >2s PDF | Eng (Platform) | Monitoring |
| Security | JWT secret leakage / weak secret | L | H | M | Rotatable secret via env, enforce min length >32 chars, secret rotation runbook | Git history scan finds secret, static scan alert | Eng (Security) | Open |
| Security | Webhook replay attacks | M | H | H | HMAC verification (Paystack), store signature + event id for idempotency (PARTIAL), enforce timestamp skew window | Duplicate event accepted, mismatch counts | Eng (Backend) | Mitigating |
| Data Integrity | Race conditions marking invoice paid twice | M | M | M | DB transaction + unique constraint on payment reference, idempotency key table | Duplicate payment rows, double metric | Eng (Backend) | Open |
| Data Integrity | Decimal rounding errors on monetary fields | L | M | L | Use Decimal with quantization, central currency util, tests on edge sums | Assertion failure in currency tests | Eng (Finance Domain) | Planned |
| Performance | N+1 queries in invoice listing | M | M | M | Eager load relationships, profiling early with test dataset | P95 list invoices >800ms | Eng (Backend) | Planned |
| Scalability | WhatsApp message burst causing blocking processing | M | H | H | Async queue (Redis) for ingestion, backpressure metrics, rate limit per issuer | Event loop backlog warnings | Eng (Platform) | Planned |
| Operational | Missing migrations drift in CI/CD | L | M | L | Alembic autogen diff check in CI (fail if pending) | CI job failing alembic diff | DevOps | Planned |
| Operational | Lack of observability (no metrics backend) | H | H | Critical | Metrics facade (DONE), integrate Prometheus + Grafana early | Unknown latency spikes reports | Eng (Platform) | Open |
| Compliance | Unencrypted PII at rest | L | H | M | Use encrypted volume, future field-level encryption (TBD) | Audit finding, external request | Eng (Security) | Planned |
| Product/Market | Low adoption due to manual onboarding friction | M | H | H | Guided WA onboarding flow, minimal required fields, referral incentives | Drop-off >40% before first invoice | Product | Open |
| Third-Party | WhatsApp Business API policy/approval delays | M | M | M | Sandbox simulation layer (stub), parallel application process | Approval pending >30 days | Ops | Monitoring |
| Third-Party | Provider pricing change increases cost per invoice | M | M | M | Cost dashboard, negotiation thresholds, multi-provider arbitrage | Cost/invoice +25% MoM | Finance | Planned |
| Legal | Misclassification of workers via informal payroll | L | H | M | Disclaimer + guidance doc, optional tax compliance module (future) | User support tickets on compliance | Legal | Planned |
| UX | Confusing error responses in chat flow | M | M | M | Unified error adapter to user-friendly prompts, test scripts | High support FAQ creation | UX | Planned |
| Business Continuity | Backup / restore gaps | M | H | H | Nightly logical dumps, RPO/RTO doc, restore drill quarterly | Failed restore test | DevOps | Planned |

## Top 5 Immediate Focus
1. Observability gap (metrics backend) – gating future performance confidence.
2. Webhook replay/idempotency robustness – financial accuracy risk.
3. Multi provider payments for resilience (Flutterwave production path).
4. WhatsApp ingestion scalability (queue) prior to marketing push.
5. PDF generation resilience & latency (warm pool / caching).

## Mitigation Roadmap (Next 3 Sprints)
- Sprint 1: Prometheus integration, idempotency table, Flutterwave live sandbox tests.
- Sprint 2: Redis queue for WhatsApp events, PDF warm-up job.
- Sprint 3: Cost dashboard (internal), encryption planning spike, N+1 profiling.

