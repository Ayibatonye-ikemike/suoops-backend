# SuoOps

WhatsApp-first invoicing platform for micro and informal businesses.

**Live at**: https://suoops.com  
**API**: https://api.suoops.com

## Stack
FastAPI, SQLAlchemy, PostgreSQL, Redis (tasks), Celery, ReportLab (PDF), Paystack (payment abstraction), S3-compatible storage.

## Quick Start
```bash
poetry install
cp .env.example .env
poetry run uvicorn app.api.main:app --reload
```

> Deployments use `requirements.txt` + `.python-version`. The repository intentionally omits `poetry.lock` to keep Heroku from detecting multiple package managers—generate it locally if you need a lockfile, but leave it untracked.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

To refresh strongly typed API bindings after backend schema updates:
1. Generate the latest schema with `npm run openapi` (writes to `src/api/types.generated.ts`).
2. Copy any changed shapes that the app uses into the curated `src/api/types.ts`, keeping the file under ~400 LOC.
3. Remove the generated file before committing, or leave it untracked per team preference.

## Directory Structure
```
app/
  api/            # FastAPI entry + routers
  bot/            # WhatsApp adapter + NLP
  core/           # config & logging
  db/             # base + session
  models/         # SQLAlchemy models & Pydantic schemas
  services/       # domain services (invoice, payment, pdf, ocr, notify)
  storage/        # S3 client abstraction
  utils/          # helpers (ids, currency, validators)
  workers/        # background tasks definitions
templates/        # HTML templates for PDF generation
tests/            # pytest suite
```

## High-Level Flow
User sends WhatsApp → webhook → NLP parse → InvoiceService → Payment link → PDF → WhatsApp send.

## Observability & Metrics

Prometheus counters & histograms are exposed via the standard `/metrics` endpoint (enabled when the `prometheus_client` library is installed). Instrumentation lives in `app/metrics.py` behind semantic helper functions.

| Metric | Description |
| ------ | ----------- |
| `invoice_created_total` | Invoices successfully created |
| `invoice_paid_total` | Invoices marked paid |
| `payment_confirmation_latency_seconds` | Histogram: time from creation to payment confirmation |
| `whatsapp_parse_unknown_total` | WhatsApp messages with unknown intent |
| `oauth_logins_total` | Successful OAuth login callbacks |
| `tax_profile_updates_total` | Tax profile update operations |
| `vat_calculations_total` | VAT summaries or calculator hits |
| `compliance_checks_total` | Tax compliance summary requests |

### Usage Pattern
Add new metrics ONLY by defining them in `app/metrics.py` and providing a helper. Call helpers from routes/services:

```python
from app.metrics import tax_profile_updated

def update_tax_profile(...):
  # business logic
  tax_profile_updated()
```

If Prometheus isn't installed, helpers become debug logs (no exceptions).

### Suggested Alerts
Examples (pseudo rules):
* Spike in VAT calculations: `increase(vat_calculations_total[5m]) > 1000`
* Low invoice creation during business hours: `sum(invoice_created_total offset 1h) < EXPECTED_MIN`

See `deploy/prometheus.yml` for base Prometheus config.

## Next Steps

## Developer Tooling: Pre-Push Git Hook

Automated local guard that runs backend `pytest` and frontend `vitest` before allowing a push.

1. Enable shared hooks path (one time):
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```
2. Attempt a push; if tests fail the push is blocked with a clear message.
3. To override (emergencies only):
```bash
SKIP_PRE_PUSH=1 git push origin main
```

Hook location: `.githooks/pre-push` (bash) – safe, idempotent, installs missing deps on first run.

Slack integration was removed (can be re-added later with a webhook secret).


## License
Proprietary (add appropriate license text).
