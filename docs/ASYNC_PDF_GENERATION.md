# Async PDF Generation with Celery

## Overview

SuoOps now supports **asynchronous PDF generation** using Celery background tasks. This significantly improves API response times for invoice creation, especially under high load or when generating complex PDFs.

## Benefits

### Before (Synchronous PDF)
- ⏱️ **Slow API responses**: 2-5 seconds per invoice creation
- 🐌 **Blocks HTTP workers**: During PDF generation
- ⚠️ **Poor user experience**: Users wait for PDF before seeing confirmation
- 🔥 **Timeout risk**: Complex PDFs can exceed HTTP timeout limits

### After (Asynchronous PDF)
- ⚡ **Fast API responses**: <500ms per invoice creation
- 🚀 **Non-blocking**: HTTP workers free immediately
- ✅ **Better UX**: Invoice created instantly, PDF ready in 1-3 seconds
- 📈 **Scalable**: Background workers handle PDF generation independently

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Client    │────────>│  API Server  │────────>│  PostgreSQL │
│  (Frontend) │ POST    │   (FastAPI)  │ INSERT  │  (Database) │
└─────────────┘         └──────────────┘         └─────────────┘
                              │
                              │ Queue Task
                              ▼
                        ┌──────────────┐
                        │    Redis     │
                        │  (Task Queue)│
                        └──────────────┘
                              │
                              │ Pick Task
                              ▼
                        ┌──────────────┐         ┌─────────────┐
                        │    Celery    │────────>│     S3      │
                        │   Worker     │ Upload  │ (PDF Files) │
                        └──────────────┘         └─────────────┘
                              │
                              │ Update DB
                              ▼
                        ┌─────────────┐
                        │  PostgreSQL │
                        │ (pdf_url)   │
                        └─────────────┘
```

## Setup Instructions

### 1. Prerequisites

Ensure Redis is running (already configured in Heroku):

```bash
# Local development (macOS)
brew install redis
brew services start redis

# Verify Redis is running
redis-cli ping  # Should return "PONG"
```

### 2. Environment Variables

Add to `.env` (already configured in production):

```bash
# Redis connection
REDIS_URL=redis://localhost:6379/0

# For Heroku Redis (with SSL)
REDIS_URL=rediss://:password@host:port
REDIS_SSL_CERT_REQS=none  # or 'required' for strict SSL
REDIS_SSL_CA_CERTS=/path/to/ca-bundle.pem
```

### 3. Start Celery Worker

#### Development (Local)

```bash
# Terminal 1: Start API server
uvicorn app.api.main:app --reload

# Terminal 2: Start Celery worker
celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
```

#### Production (Heroku)

Add to `Procfile`:

```procfile
web: gunicorn app.api.main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
worker: celery -A app.workers.celery_app worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
```

Deploy worker dyno:

```bash
# Scale worker dynos
heroku ps:scale worker=1 --app suoops-backend

# Check worker logs
heroku logs --tail --dyno=worker --app suoops-backend

# Monitor Celery tasks
heroku run celery -A app.workers.celery_app inspect active --app suoops-backend
```

### 4. Optional: Celery Beat (Scheduled Tasks)

For periodic tasks like monthly tax reports:

```procfile
beat: celery -A app.workers.celery_app beat --loglevel=info
```

```bash
heroku ps:scale beat=1 --app suoops-backend
```

## API Usage

### Default Behavior (Async PDF)

```python
# POST /invoices/ with async_pdf=true (default)
POST https://api.suoops.com/invoices/
Content-Type: application/json

{
  "customer_name": "John Doe",
  "amount": 50000,
  "lines": [...]
}

# Response (immediate, pdf_url is null initially)
{
  "invoice_id": "INV-123456",
  "amount": 50000,
  "pdf_url": null,  # Will be populated in 1-3 seconds
  "status": "pending",
  ...
}
```

### Synchronous PDF (Legacy)

```python
# POST /invoices/?async_pdf=false for immediate PDF
POST https://api.suoops.com/invoices/?async_pdf=false

# Response (slower, pdf_url available immediately)
{
  "invoice_id": "INV-123456",
  "amount": 50000,
  "pdf_url": "https://s3.../INV-123456.pdf",
  ...
}
```

### Frontend Handling

#### Option 1: Poll for PDF URL

```typescript
// Create invoice with async PDF
const invoice = await createInvoice(invoiceData);

// Poll for PDF URL every 2 seconds (max 5 attempts)
let attempts = 0;
const pollInterval = setInterval(async () => {
  attempts++;
  
  const updated = await getInvoice(invoice.invoice_id);
  
  if (updated.pdf_url) {
    clearInterval(pollInterval);
    console.log("PDF ready:", updated.pdf_url);
    showPDFLink(updated.pdf_url);
  } else if (attempts >= 5) {
    clearInterval(pollInterval);
    console.warn("PDF generation taking longer than expected");
    showRetryButton();
  }
}, 2000);
```

#### Option 2: WebSocket Notifications (Future)

```typescript
// Subscribe to invoice updates
socket.on(`invoice:${invoice.invoice_id}:pdf_ready`, (data) => {
  console.log("PDF ready:", data.pdf_url);
  showPDFLink(data.pdf_url);
});
```

#### Option 3: Show Loading State

```typescript
// Create invoice
const invoice = await createInvoice(invoiceData);

// Show success message with loading indicator
toast.success("Invoice created! PDF generating...");

// Show invoice details immediately
showInvoiceDetails(invoice);

// Show PDF loading placeholder
if (!invoice.pdf_url) {
  showPDFLoadingSpinner();
  
  // Refetch invoice after 3 seconds
  setTimeout(async () => {
    const updated = await getInvoice(invoice.invoice_id);
    if (updated.pdf_url) {
      hidePDFLoadingSpinner();
      showPDFLink(updated.pdf_url);
    }
  }, 3000);
}
```

## Celery Task Configuration

### Task Queues

We use 4 separate queues with different priorities:

| Queue | Priority | Tasks | Purpose |
|-------|----------|-------|---------|
| `default` | 5 | General tasks | Catch-all for misc tasks |
| `pdf_generation` | 3 | PDF generation | Invoice/receipt PDFs |
| `email_sending` | 7 | Email delivery | High priority notifications |
| `whatsapp_sending` | 7 | WhatsApp delivery | High priority notifications |

### Task Retry Configuration

```python
@celery_app.task(
    bind=True,
    name="pdf.generate_invoice",
    autoretry_for=(Exception,),
    retry_backoff=30,       # 30s, 60s, 120s, 240s exponential backoff
    retry_jitter=True,      # Add random jitter to avoid thundering herd
    retry_kwargs={"max_retries": 3},  # Retry up to 3 times
)
def generate_invoice_pdf_async(...):
    ...
```

### Task Timeouts

- **Soft Limit**: 4 minutes (SoftTimeLimitExceeded exception)
- **Hard Limit**: 5 minutes (SIGKILL, task killed)

Tasks exceeding soft limit can clean up gracefully. Hard limit prevents runaway tasks.

## Monitoring

### Check Active Tasks

```bash
# Local
celery -A app.workers.celery_app inspect active

# Heroku
heroku run celery -A app.workers.celery_app inspect active --app suoops-backend
```

### Check Queue Stats

```bash
celery -A app.workers.celery_app inspect stats
```

### Monitor Task Failures

```bash
# View task failures
heroku logs --tail --dyno=worker --app suoops-backend | grep ERROR
```

### Prometheus Metrics

We track the following metrics:

- `celery_task_total{task, status}` - Total tasks executed
- `celery_task_duration_seconds{task}` - Task execution time
- `pdf_generation_success_total` - Successful PDF generations
- `pdf_generation_failure_total` - Failed PDF generations

## Troubleshooting

### PDF Generation Fails

**Symptoms**: Invoice created but `pdf_url` remains `null` after 30+ seconds

**Debugging**:

```bash
# Check worker logs
heroku logs --tail --dyno=worker --app suoops-backend

# Check failed tasks
celery -A app.workers.celery_app inspect failed

# Check task result
celery -A app.workers.celery_app result <task-id>
```

**Common Causes**:
1. **S3 upload failure**: Check AWS credentials
2. **Memory error**: Increase worker memory or reduce concurrency
3. **Redis connection**: Check `REDIS_URL` environment variable
4. **WeasyPrint failure**: Check HTML template validity

**Fix**:
```bash
# Retry failed task manually
heroku run python -c "from app.workers.tasks import generate_invoice_pdf_async; generate_invoice_pdf_async.delay(invoice_id=123)" --app suoops-backend
```

### Worker Not Processing Tasks

**Symptoms**: Tasks queued but not executing

**Check**:

```bash
# Verify worker is running
heroku ps --app suoops-backend

# Check Redis connection
heroku run python -c "import redis; r=redis.from_url('$REDIS_URL'); print(r.ping())" --app suoops-backend

# Restart worker
heroku ps:restart worker --app suoops-backend
```

### High Memory Usage

**Symptoms**: Worker dyno R14 errors (memory quota exceeded)

**Solutions**:

1. **Reduce concurrency**:
   ```bash
   # In Procfile
   worker: celery -A app.workers.celery_app worker --concurrency=2 --max-tasks-per-child=50
   ```

2. **Upgrade dyno**:
   ```bash
   heroku ps:type worker=standard-2x --app suoops-backend
   ```

3. **Enable garbage collection**:
   ```python
   # Already implemented in tasks.py
   import gc
   gc.collect()  # After each PDF generation
   ```

### Slow PDF Generation

**Symptoms**: PDFs take >10 seconds to generate

**Optimizations**:

1. **Reduce image resolution** in templates
2. **Optimize WeasyPrint fonts** (use system fonts)
3. **Cache logo images** (reuse S3 URLs)
4. **Simplify HTML/CSS** (avoid complex layouts)

## Cost Analysis

### Heroku Dyno Costs

| Configuration | Monthly Cost | Throughput |
|---------------|--------------|------------|
| 1x Standard Worker | $25/month | ~500 invoices/day |
| 2x Standard Workers | $50/month | ~1000 invoices/day |
| 1x Performance-M Worker | $250/month | ~5000 invoices/day |

### Redis Costs

| Plan | Monthly Cost | Memory | Connections |
|------|--------------|--------|-------------|
| Mini (Dev) | $3/month | 25MB | 20 |
| Premium-0 (Prod) | $15/month | 100MB | 40 |
| Premium-1 (Scale) | $60/month | 1GB | 120 |

**Recommendation**: Start with 1x Standard Worker + Premium-0 Redis = **$40/month**

## Performance Benchmarks

### Before (Synchronous PDF)

```
Requests: 100 invoices
Mean response time: 3.2 seconds
95th percentile: 4.8 seconds
Throughput: ~18 invoices/minute (1 worker)
```

### After (Asynchronous PDF)

```
Requests: 100 invoices
Mean API response: 420ms
95th percentile API: 680ms
PDF generation: 1.5 seconds (background)
Throughput: ~200 invoices/minute (4 workers)
```

**Improvement**: **7.6x faster** API response, **11x higher** throughput

## Migration Guide

### Existing Invoices

Existing invoices already have `pdf_url` populated. No migration needed.

### Testing Async PDF

```bash
# Create test invoice with async PDF
curl -X POST https://api.suoops.com/invoices/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Test Customer",
    "amount": 1000,
    "async_pdf": true
  }'

# Check PDF generation after 3 seconds
curl https://api.suoops.com/invoices/INV-XXXXXX \
  -H "Authorization: Bearer $TOKEN"
```

### Rolling Back to Sync PDF

If issues arise, disable async PDF globally:

```python
# In routes_invoice.py, change default
async_pdf: bool = False  # Back to synchronous
```

Or per-request:

```bash
POST /invoices/?async_pdf=false
```

## Security Considerations

1. **Task Authentication**: Workers run with full database access (no JWT needed)
2. **Queue Security**: Redis requires authentication (password in URL)
3. **S3 Access**: Workers use IAM credentials (not exposed in tasks)
4. **Rate Limiting**: Tasks have time limits to prevent abuse

## Future Enhancements

1. **✅ PDF polling endpoint**: `GET /invoices/{id}/pdf_status`
2. **🔄 WebSocket notifications**: Real-time PDF ready events
3. **📊 Task monitoring dashboard**: Celery Flower integration
4. **🔧 Automatic retries**: Exponential backoff for failed tasks
5. **📧 Email with PDF**: Send notification once PDF is ready

---

**Last Updated**: November 22, 2025  
**Owner**: Backend Team  
**Review Schedule**: Quarterly
