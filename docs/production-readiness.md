# Production Readiness Guide

This document captures the baseline configuration and operational runbooks required to ship WhatsInvoice into a production environment.

## Infrastructure
- **Containers**: Use the provided `Dockerfile` together with `deploy/docker-compose.yaml` to launch API+worker, Postgres, Redis, and MinIO locally or in staging. For Kubernetes, treat each compose service as a Deployment/StatefulSet.
- **Database**: Run Postgres 15+ with automated backups. Apply schema migrations using `poetry run alembic upgrade head` during deploys.
- **Object storage**: MinIO (compose) or AWS S3 in production. Ensure buckets are versioned and encrypted at rest.
- **Queues**: Redis 7 powers Celery task routing; deploy in cluster mode for HA. Configure Redis AUTH when exposed outside a private network.
- **Secrets**: Load configuration via environment variables or a secrets manager (AWS Parameter Store, Vault). Never bake secrets into images.

## Observability
- **Logging**: Structured JSON logging is enabled by setting `LOG_FORMAT=json` (already the default in docker-compose). Forward logs to your aggregator (CloudWatch, ELK, etc.).
- **Metrics**: `/metrics` exposes Prometheus-compatible metrics. `deploy/prometheus.yml` gives a starter scrape config.
- **Health checks**: `/healthz` performs a DB connectivity test; wire to load-balancer health probes.
- **Tracing**: Instrumentation hooks are TODO—consider OpenTelemetry SDK integration for request tracing if needed.

## Security & Compliance
- **Transport security**: Terminate TLS at your ingress/load-balancer; enforce HTTPS by setting `APP_ENV=prod` (auto enables redirect + security headers).
- **Authentication**: Access/refresh tokens with explicit validation; enforce password complexity in `AuthService`.
- **Rate limiting**: SlowAPI-backed limits on auth endpoints prevent brute-force attacks; configure Redis storage in production.
- **Webhook integrity**: Paystack signatures validated with shared secret; webhook idempotency persisted in `webhookevent` table.
- **Secrets hygiene**: Provide mandatory secrets in production via environment or secret manager; config validation will refuse missing values.

## Operations
- **Deploy**:
  1. `poetry run ruff check && poetry run pytest`
  2. `docker compose -f deploy/docker-compose.yaml build`
  3. Run DB migrations (`poetry run alembic upgrade head`).
  4. Roll out containers (compose, ECS, or Kubernetes).
- **Workers**: Start background tasks with `poetry run celery-worker` (the Poetry script wraps `app.workers.worker:main`).
- **Backups**: Snapshot Postgres daily and mirror MinIO/S3 buckets; test restores quarterly.
- **Smoke tests**: After deploy, hit `/healthz`, `/metrics`, and run `tests/test_smoke.py` against the staging environment.
- **Incidents**: Enable alerting on Prometheus scrape failures, high webhook errors, and Celery retry counts. Document escalation contacts alongside this file.

Keep this checklist current as infrastructure matures—track future improvements (OpenTelemetry, WAF rules, automated DR drills) in the issue tracker.
