# Architecture Evolution Plan

## Phase 0 (Now) – Structured Monolith
- FastAPI app with clear domain service classes (Invoices, Payroll, Payments, WhatsApp, NLP, PDF, Auth)
- Single Postgres DB, Alembic migrations
- Payment provider abstraction + metrics façade in-process
- Strength: Minimal latency, low cognitive overhead
- Risk: Shared DB coupling if teams scale

## Phase 1 – Operational Hardening (Sprints 1-3)
Goals: Observability, resilience, correctness.
- Add Prometheus metrics exporter + Grafana dashboards (latency, error rate, payment success, PDF time)
- Introduce Redis for: (a) WhatsApp message queue (ingest buffering) (b) Future task scheduling
- Idempotency persistence table for webhooks / payment updates
- Structured logging (JSON) + correlation IDs

## Phase 2 – Async & Workflows
Trigger: P95 latency >1s OR >3 blocking external calls per request.
- Introduce background worker (Celery or RQ) for PDF generation, payment reconciliation, large payroll runs
- Event outbox table + dispatcher for domain events (invoice.created, payment.failed)
- Retry & DLQ policies (exponential backoff)

## Phase 3 – Service Extraction Candidates
Decompose only when bounded contexts show independent scaling or change cadence.
1. Payments Service: Owns provider integrations, webhooks, reconciliation.
2. Messaging Service: WhatsApp + future channels (email, SMS) with templating.
3. Reporting/Analytics: Pre-aggregations, dashboards, ledger integrity checks.

Criteria for extraction:
- >30% of prod incidents sourced from a module
- Independent scaling need (CPU-bound PDF vs I/O-bound payments)
- Team boundary (dedicated squad) or deployment risk isolation

## Phase 4 – Data Segmentation / Multi-Tenancy
- Row-level scoping already via issuer_id; evolve to schema-per-tenant or cluster-tiering if high-value enterprise tenants emerge.
- Introduce read replicas for analytics heavy queries.

## Phase 5 – Intelligence & Automation Layer
- Replace rule-based NLP with fine-tuned lightweight model (Distil variant) + fallback rules
- Predictive cash-flow insights (spend/receivables forecasting)
- Auto reconciliation suggestions for partial or failed payments

## Phase 6 – Compliance & Extensibility
- Plugin/extension system for local regulatory modules (VAT rules, withholding tax)
- Audit event stream to WORM storage
- Field-level encryption for PII (envelope key strategy)

## Cross-Cutting Concerns Timeline
| Concern | Current | Target Milestone |
|---------|---------|------------------|
| Metrics | Facade only | Prometheus Phase 1 |
| Tracing | None | OpenTelemetry Phase 2 |
| Caching | None | Redis Phase 1 (hot PDF, invoice list) |
| Rate Limiting | None | Phase 2 (per issuer WA events) |
| DR/BCP | Manual backups | Automated + restore drill Phase 3 |
| Security Posture | Basic JWT | Rotation + scopes Phase 2, field encryption Phase 6 |

## Decision Log (Living)
| Decision | Date | Status | Rationale | Revisit |
|----------|------|--------|-----------|---------|
| Monolith-first | T0 | Active | Speed & clarity | Re-eval Phase 3 |
| Payment abstraction early | T0 | Active | Avoid rewrite when 2nd provider lands | Keep |
| HTML→PDF behind flag | T0 | Active | Reduce build risk | When stable |
| Metrics facade w/o backend | T0 | Active | Ship instrumented code early | After Prometheus |

## Exit Criteria Per Phase
- Phase 1 complete: Dashboards + queue + idempotency + structured logs.
- Phase 2 complete: Worker + outbox + basic tracing.
- Phase 3 triggered: Extraction metrics threshold hit.

