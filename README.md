# WhatsInvoice MVP

WhatsApp-first invoicing platform for micro and informal businesses.

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

## Next Steps
- Implement actual WhatsApp send logic
- Implement payment provider API calls
- Flesh out PDF styling
- Add authentication & dashboard (future sprint)

## License
Proprietary (add appropriate license text).
