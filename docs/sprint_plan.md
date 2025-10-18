# Sprint Plan (Initial 3 Sprints)
Timebox assumption: 2-week sprints, small founding team.

## Sprint 1 – Stabilize Core Invoicing
Goals:
- Auth + Invoice + Payment (Paystack) happy path hardened
- Discount field live with migration
- PDF fallback reliable
Deliverables:
- Paystack live test success
- Invoice creation & payment e2e test
- Idempotent payment webhook test (DONE)
Definition of Done:
- Tests green, P95 invoice create <400ms, no critical lint
Stretch:
- Basic Prometheus stub endpoint

## Sprint 2 – Payroll & Observability Foundations
Goals:
- Payroll issuer derivation (DONE now for routes/services)
- Metrics backend integration (Prometheus + Grafana dashboard v1)
- WhatsApp ingestion queue scaffold (Redis)
- Flutterwave sandbox integration (charge + webhook)
Deliverables:
- Dashboard panels: latency, error_rate, payment_success_ratio
- Dual provider payment test (simulated)
Definition of Done:
- Queue buffers messages; no data loss in burst test (simulated 200 msg)
Stretch:
- Tracing prototype (OpenTelemetry)

## Sprint 3 – Resilience & Intelligence Prep
Goals:
- Outbox + retry for webhooks
- PDF warm cache + pre-render for recent invoices
- NLP intent expansion (recognize partial payments, due in X days)
- Cost monitoring script
Deliverables:
- Outbox table + worker consumer
- Expanded NLP tests
Definition of Done:
- No lost events in induced failure test (kill worker mid-process)
Stretch:
- Basic anomaly detection script (spend spikes)

## Capacity / Estimation Notes
- Team velocity initially unknown; bias for under-commit.
- Target 70% planned, 30% buffer.

## Roles (Lightweight)
- Backend: Core services, DB, payments, metrics
- Platform: Infra, queues, observability, build
- Product/UX: Chat flows, adoption funnel, wording

