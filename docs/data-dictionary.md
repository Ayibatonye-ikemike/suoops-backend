# Data Dictionary

Defines core data entities, fields, purpose, and classification for Suoops.

| Entity | Field | Type | Purpose | Classification | Notes |
|--------|-------|------|---------|---------------|-------|
| User | id | int | Unique identifier | Internal | Auto increment |
| User | email | str | Login & notifications (plaintext for app use) | PII | Nullable (phone users) |
| User | email_enc | str | Encrypted email (pilot) | Sensitive | May be null until migration |
| User | phone | str | Login & notifications | PII | E.164 format |
| User | name | str | Display & invoices | PII | Business or personal name |
| User | business_name | str | Invoice display | PII | If different from name |
| User | plan | enum | Subscription tier gating | Internal | FREE/STARTER/PRO/BUSINESS/ENTERPRISE |
| User | invoices_this_month | int | Quota enforcement | Internal | Derived counter |
| User | logo_url | str | Branding on invoices | Internal | S3 object URL |
| User | role | str | RBAC decisions | Internal | user/staff/admin |
| Invoice | id | int | Internal primary key | Internal | |
| Invoice | invoice_id | str | External reference & QR | Internal | UUID or short id |
| Invoice | issuer_id | int | Owner business linkage | Internal | FK user.id |
| Invoice | customer_id | int | Customer linkage | PII | FK customer.id |
| Invoice | amount | decimal | Total charge | Internal | Stored in minor units? |
| Invoice | status | enum | Lifecycle state | Internal | draft/paid/refunded |
| Invoice | created_at | timestamp | Audit & ordering | Internal | UTC |
| Invoice | pdf_url | str | Access to PDF | Internal | Presigned or local path |
| InvoiceLine | id | int | Line item | Internal | |
| InvoiceLine | invoice_id | int | Parent invoice | Internal | FK invoice.id |
| InvoiceLine | description | str | Item description | Internal | Customer visible |
| InvoiceLine | quantity | int | Item quantity | Internal | |
| InvoiceLine | unit_price | decimal | Price per unit | Internal | |
| Customer | id | int | Internal primary key | Internal | |
| Customer | name | str | Invoice display | PII | Masked in public verify |
| Customer | email | str | Invoice delivery | PII | Optional |
| Customer | phone | str | Invoice delivery | PII | Optional |
| WebhookEvent | id | int | Audit trail | Internal | |
| WebhookEvent | provider | str | Source system | Internal | paystack/etc |
| WebhookEvent | event_type | str | Event classification | Internal | subscription_update/payment |
| WebhookEvent | payload | json | Raw event data | Sensitive | Consider pruning PII |
| WebhookEvent | processed_at | timestamp | Processing status | Internal | Nullable until handled |

## Classification Legend
- PII: Directly identifies or can identify a natural person.
- Internal: Operational data not containing personal identifiers.
- Sensitive: Data requiring additional controls (tokens, raw webhook payloads containing personal info).

## Usage Notes
- Column-level encryption candidates: `User.email`, `Customer.email`, `Customer.phone` if threat model expands.
- Regular purge candidate: Stale `WebhookEvent.payload` after normalization (e.g. 30 days).
- Derived counters (`invoices_this_month`) should be recomputable; maintain integrity via periodic reconciliation job.

## Update Process
1. Add new field → update this dictionary in same PR.
2. Tag classification → ensure corresponding privacy controls (masking in public endpoints, encryption if needed).
3. Review quarterly for accuracy.

---
Owned by: Platform Engineering / Compliance
Last Updated: YYYY-MM-DD