# SuoOps Infrastructure Guide

> Last updated: 20 February 2026

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USERS (Nigeria)                         │
└──────────────┬───────────────────────────────┬──────────────────┘
               │                               │
        WhatsApp Cloud API              HTTPS (browser)
               │                               │
               ▼                               ▼
┌──────────────────────┐          ┌──────────────────────┐
│   Meta Webhook       │          │   Vercel (US-East)   │
│   → api.suoops.com   │          │   suoops.com         │
└──────────┬───────────┘          │   support.suoops.com │
           │                      └──────────┬───────────┘
           ▼                                 │
┌──────────────────────────────────────────────────────────────┐
│                    Render (Oregon, US)                        │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ FastAPI (web)    │  │ Celery Worker   │  │ Redis       │  │
│  │ Gunicorn 1w/2t   │  │ concurrency=1   │  │ (broker +   │  │
│  │ Starter (512MB)  │  │ Starter (512MB) │  │  cache)     │  │
│  └────────┬─────────┘  └────────┬────────┘  └─────────────┘  │
│           │                     │                             │
│           ▼                     ▼                             │
│  ┌──────────────────────────────────────────┐                │
│  │  PostgreSQL 16 (Starter)                 │                │
│  │  No connection pooling · No replicas     │                │
│  └──────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

### Current Stack

| Component       | Service          | Plan    | Region  | Cost/mo |
|-----------------|------------------|---------|---------|---------|
| Frontend        | Vercel           | Pro     | iad1    | $20     |
| Backend API     | Render Web       | Starter | Oregon  | $7      |
| Celery Worker   | Render Worker    | Starter | Oregon  | $7      |
| PostgreSQL      | Render Database  | Starter | Oregon  | $7      |
| Redis           | Render Redis     | Free    | Oregon  | $0      |
| Domain/DNS      | Cloudflare       | Free    | —       | $0      |
| WhatsApp API    | Meta Cloud API   | Free    | —       | $0*     |
| Email (SMTP)    | Brevo            | Free    | —       | $0      |
| Payments        | Paystack         | —       | —       | 1.5%    |
| Error Tracking  | Sentry           | Free    | —       | $0      |
| **Total**       |                  |         |         | **~$41/mo** |

> *WhatsApp Cloud API: first 1,000 service conversations/mo are free.

### Current Limitations

| Risk                        | Impact                                                    |
|-----------------------------|-----------------------------------------------------------|
| **Downtime on every deploy** | Render Starter restarts the single process — no rolling deploys |
| **512MB memory ceiling**    | WeasyPrint PDF generation + Gunicorn in 512MB is tight    |
| **1 Gunicorn worker**       | A blocked request (PDF gen, slow DB query) stalls all traffic |
| **No DB connection pooling**| Under load, connection exhaustion causes 500 errors       |
| **Servers in US, users in Nigeria** | ~200ms latency per API call                     |
| **No uptime monitoring**    | Nobody gets alerted if the API goes down                  |
| **No CI/CD pipeline**       | Manual `git push` deploys with no automated testing gate  |
| **No backup verification**  | DB backups exist but are never tested                     |

---

## Growth Roadmap

### 🟢 Stage 1 — Quick Wins (Now)

**Goal:** Zero-downtime deploys, proper monitoring, stay on Render.

| Change                          | Why                                                        | Cost     |
|---------------------------------|------------------------------------------------------------|----------|
| Render **Standard** web plan    | Rolling deploys, 1GB RAM, 2+ Gunicorn workers              | +$18/mo  |
| Render **Standard** worker plan | More memory for PDF generation in Celery                   | +$18/mo  |
| Render **Pro** Postgres         | Connection pooling (PgBouncer), daily backups, read replica | +$43/mo  |
| **Uptime monitoring** (BetterStack or UptimeRobot) | Alert via SMS/email when API goes down | Free     |
| **Sentry** on backend           | Error alerting, performance traces (already on frontend)   | Free     |
| **GitHub Actions CI**           | Run `pytest` before every deploy — never ship broken code  | Free     |

**Estimated total: ~$120/mo**

#### GitHub Actions CI (suggested workflow)

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest tests/ -x -q
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          ENV: test
```

---

### 🟡 Stage 2 — Scale for Growth (100–500 users)

**Goal:** Lower latency for Nigerian users, autoscaling, managed services.

| Component     | Migrate To           | Why                                                      |
|---------------|----------------------|----------------------------------------------------------|
| **Compute**   | **Fly.io**           | Johannesburg region (closest to Nigeria), rolling deploys, autoscale, Docker-native |
| **Database**  | **Neon** or **Supabase** | Serverless Postgres, connection pooling, branching for dev |
| **Redis**     | **Upstash**          | Serverless, per-request pricing, multi-region replication |
| **PDF Worker**| Separate Fly machine | Isolate WeasyPrint so it doesn't block API requests      |
| **CDN/WAF**   | **Cloudflare Pro**   | Nigerian edge PoPs, DDoS protection, bot filtering       |
| **Logging**   | **Grafana Cloud**    | Centralized logs, dashboards, free tier generous          |

**Why Fly.io fits SuoOps:**
- Your existing `Dockerfile` works with zero changes
- `fly deploy` gives rolling deploys with health-check gates
- Johannesburg is ~50ms from Lagos vs ~200ms from Oregon
- Scale to zero when idle (no cost during off-hours)
- Private networking between API, worker, and database

#### Fly.io config (example)

```toml
# fly.toml
app = "suoops-backend"
primary_region = "jnb"  # Johannesburg

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1

  [http_service.concurrency]
    type = "requests"
    hard_limit = 250
    soft_limit = 200

[[http_service.checks]]
  grace_period = "10s"
  interval = "15s"
  method = "GET"
  path = "/ready"
  timeout = "5s"

[processes]
  app = "gunicorn app.api.main:app -k uvicorn.workers.UvicornWorker -w 2 --timeout 60 --bind 0.0.0.0:8000"
  worker = "celery -A app.workers.celery_app worker --loglevel=info --concurrency=2"

[[vm]]
  size = "shared-cpu-1x"
  memory = "1gb"
```

**Estimated total: ~$50–80/mo** (competitive with Render Standard)

---

### 🔴 Stage 3 — Production-Grade (500+ users, enterprise/compliance)

**Goal:** High availability, automatic failover, security compliance, audit-ready.

```
┌───────────────────────────────────────────────────────────────────────┐
│                        Cloudflare (Edge)                              │
│  WAF · DDoS · Rate Limiting · Edge Cache · Nigerian PoPs             │
└──────────────┬────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     AWS eu-west-1 (Ireland)                          │
│                     or af-south-1 (Cape Town)                        │
│                                                                      │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐  │
│  │ ECS Fargate (API)            │  │ ECS Fargate (Worker)         │  │
│  │ Auto-scaling: 2–10 tasks     │  │ Auto-scaling: 1–5 tasks      │  │
│  │ Rolling deploy (0 downtime)  │  │ Spot capacity for cost       │  │
│  │ Health-check gated           │  │                              │  │
│  └──────────┬───────────────────┘  └──────────┬───────────────────┘  │
│             │                                  │                      │
│             ▼                                  ▼                      │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ RDS PostgreSQL 16    │  │ ElastiCache Redis                   │  │
│  │ Multi-AZ failover    │  │ Cluster mode · Persistence          │  │
│  │ Read replica         │  │                                      │  │
│  │ Automated backups    │  │                                      │  │
│  │ Point-in-time        │  │                                      │  │
│  │ recovery (35 days)   │  │                                      │  │
│  └──────────────────────┘  └──────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ S3 (invoices, PDFs)  │  │ CloudWatch / Datadog                │  │
│  │ Versioned · Encrypted│  │ APM · Logs · Metrics · Alerts       │  │
│  └──────────────────────┘  └──────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Secrets Manager      │  │ SQS (replace Celery/Redis broker)   │  │
│  │ Auto-rotate keys     │  │ Dead-letter queues · No broker ops  │  │
│  └──────────────────────┘  └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

| Component       | Service                   | Why                                           |
|-----------------|---------------------------|-----------------------------------------------|
| Compute         | AWS ECS Fargate            | Auto-scaling, rolling deploys, no servers      |
| Database        | AWS RDS PostgreSQL Multi-AZ| Automatic failover, point-in-time recovery     |
| Cache/Queue     | AWS ElastiCache Redis      | Clustered, persistent, Multi-AZ                |
| Object Storage  | AWS S3                     | Invoice PDFs, logos, exports — encrypted at rest|
| Queue (alt)     | AWS SQS                    | Replace Celery broker — managed, no Redis deps |
| CDN/WAF         | Cloudflare Pro             | Nigerian edge, bot protection, rate limiting   |
| Secrets         | AWS Secrets Manager        | Rotate API keys without redeploying            |
| Monitoring      | Datadog or Grafana Cloud   | APM, distributed tracing, log aggregation      |
| CI/CD           | GitHub Actions → ECR → ECS | Automated test → build → blue/green deploy     |
| DNS             | Cloudflare                 | Already in use                                 |

**Estimated total: ~$200–400/mo** (mostly RDS + Fargate)

---

## Security Best Practices

### Already Implemented ✅
- [x] CSRF protection on all state-changing endpoints
- [x] Rate limiting on auth/OTP endpoints
- [x] Input validation via Pydantic schemas
- [x] SQL injection prevention (SQLAlchemy ORM)
- [x] HTTPS enforced (Render + Vercel)
- [x] Secure session cookies (HttpOnly, SameSite)
- [x] Sentry error tracking (frontend)
- [x] Health check endpoint (`/ready`)
- [x] Webhook signature verification (Paystack, WhatsApp)

### Should Add 🟡
- [ ] **Sentry on backend** — currently frontend only
- [ ] **Uptime monitoring** — BetterStack, UptimeRobot, or Checkly
- [ ] **Automated backups testing** — restore a backup monthly
- [ ] **GitHub Actions CI** — pytest gate before deploy
- [ ] **Dependency scanning** — Dependabot or Snyk for CVEs
- [ ] **Database connection pooling** — PgBouncer (comes with Render Pro Postgres)
- [ ] **Log retention policy** — ship logs to Grafana Cloud or Datadog

### Future (Stage 3) 🔴
- [ ] **WAF rules** — Cloudflare Pro managed ruleset
- [ ] **Secrets rotation** — AWS Secrets Manager or Vault
- [ ] **SOC 2 / NDPR compliance** — audit trail, data residency
- [ ] **Penetration testing** — annual third-party pen test
- [ ] **Disaster recovery plan** — documented RTO/RPO targets
- [ ] **Multi-region failover** — active-passive across regions

---

## Zero-Downtime Deploy Checklist

### Render (Current)
1. Upgrade to **Standard** plan (required for rolling deploys)
2. Ensure `/ready` health check returns 200 only when app is ready
3. Render will keep old instance running until new one passes health check

### Fly.io (Recommended)
1. `fly deploy` performs rolling deploy by default
2. Health check at `/ready` gates traffic cutover
3. `min_machines_running = 1` ensures always-on
4. Blue/green via `fly deploy --strategy=bluegreen`

### AWS ECS (Enterprise)
1. Blue/green deployment via CodeDeploy
2. ALB health checks gate traffic shift
3. Automatic rollback on health check failure
4. Zero-downtime database migrations via `expand-contract` pattern

---

## Database Migration Strategy (Zero-Downtime)

When migrating databases between providers:

```
1. Set up new database (Neon/RDS/Supabase)
2. Enable logical replication from old → new
3. Point app to new database (env var change)
4. Verify data integrity
5. Decommission old database

Alternative (small DB):
1. Put app in maintenance mode
2. pg_dump old → pg_restore new
3. Update DATABASE_URL
4. Redeploy
```

---

## Monitoring & Alerting Setup

### Minimum Viable Monitoring
```
┌────────────────┐     ┌──────────────┐     ┌──────────────┐
│ UptimeRobot    │     │ Sentry       │     │ Render       │
│ Check /ready   │────▶│ Error alerts │────▶│ Deploy logs  │
│ every 5 min    │     │ Slack/email   │     │ Auto-restart │
└────────────────┘     └──────────────┘     └──────────────┘
```

### Production Monitoring (Stage 3)
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Datadog APM  │  │ CloudWatch   │  │ PagerDuty    │  │ Grafana      │
│ Traces       │  │ Metrics      │  │ On-call      │  │ Dashboards   │
│ Latency p99  │  │ CPU/Memory   │  │ Escalation   │  │ Business KPI │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

### Key Metrics to Track
| Metric                     | Alert Threshold     | Tool          |
|----------------------------|---------------------|---------------|
| API response time (p95)    | > 2 seconds         | Sentry/Datadog|
| Error rate (5xx)           | > 1% of requests    | Sentry        |
| Uptime                     | < 99.9%             | UptimeRobot   |
| Database connections       | > 80% of pool       | Grafana       |
| Memory usage               | > 85%               | Render/Fly    |
| Celery queue depth         | > 100 pending tasks | Grafana       |
| Invoice creation latency   | > 5 seconds         | Sentry        |
| WhatsApp webhook response  | > 10 seconds        | Sentry        |

---

## Cost Comparison Summary

| Stage   | Monthly Cost | What You Get                                    |
|---------|-------------|-------------------------------------------------|
| Current | ~$41        | Works but fragile — downtime on deploys          |
| Stage 1 | ~$120       | Zero-downtime, monitoring, CI/CD, connection pool|
| Stage 2 | ~$50–80     | Lower latency (Africa region), autoscaling       |
| Stage 3 | ~$200–400   | Enterprise-grade HA, compliance-ready            |

---

## Decision Matrix

| If you need...                    | Go with...       |
|-----------------------------------|------------------|
| Quick fix, stay on Render         | **Stage 1**      |
| Best value + Africa latency       | **Stage 2 (Fly.io)** |
| SOC 2 / NDPR compliance           | **Stage 3 (AWS)** |
| Lowest possible cost              | **Stage 1** (Render Standard) |
| Fastest migration                 | **Stage 2** (Dockerfile works as-is) |
