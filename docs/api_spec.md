# WhatsInvoice API Spec (MVP)

Version: 0.1.0

## Auth

### POST /auth/register
Request:
```
{ "phone": "+2348012345678", "name": "Jane", "password": "secret123" }
```
Response 200:
```
{ "id": 1, "phone": "+2348012345678", "name": "Jane" }
```

### POST /auth/login
Request:
```
{ "phone": "+2348012345678", "password": "secret123" }
```
Response 200:
```
{ "access_token": "<jwt>", "token_type": "bearer" }
```

Authorization: `Authorization: Bearer <jwt>`

## Invoices

### POST /invoices/
Create invoice (issuer inferred later; currently pass `issuer_id`).
Request:
```
{
  "issuer_id": 1,
  "customer_name": "Tolu",
  "amount": "25000",
  "lines": [ {"description": "2 wigs", "quantity": 1, "unit_price": "25000" } ]
}
```
Response:
```
{ "invoice_id": "INV-...", "amount": "25000", "status": "pending", "pdf_url": "https://..." }
```

### GET /invoices/
List recent invoices.
Response:
```
[
  { "invoice_id": "INV-...", "amount": "25000", "status": "pending", "pdf_url": "https://..." }
]
```

### POST /invoices/payments/webhook
Internal consumption of payment events (legacy stub). Use `/webhooks/paystack` for real Paystack webhooks.

## Payroll

### POST /payroll/workers
```
{ "issuer_id": 1, "name": "Worker A", "daily_rate": "5000" }
```
Response:
```
{ "id": 3, "name": "Worker A", "daily_rate": "5000" }
```

### POST /payroll/runs
```
{ "issuer_id": 1, "period_label": "2025-W40", "days": { "3": 5 } }
```
Response (simplified):
```
{ "id": 2, "period_label": "2025-W40", "total_gross": "25000", "records": [ { "worker_id": 3, "gross_pay": "25000", "net_pay": "25000" } ] }
```

## Webhooks

### POST /webhooks/whatsapp
Payload (simplified example):
```
{ "from": "+2348012345678", "text": "Invoice Joy 12000 due tomorrow" }
```
Response:
```
{ "ok": true }
```

### POST /webhooks/paystack
Headers: `x-paystack-signature: <hmac>`
Body: Paystack event JSON. Service verifies signature and updates invoice status.

## Entities Summary

Invoice: invoice_id, issuer_id, customer (name, phone), amount, status, due_date, pdf_url.
PayrollRun: issuer_id, period_label, total_gross, records (worker_id, days, gross, net).
User: id, phone, name.

## Future (Not Yet Implemented)
- Pagination & filtering
- OAuth-style token refresh
- Real WhatsApp delivery statuses
- Flutterwave provider abstraction
- OCR draft invoice endpoint
