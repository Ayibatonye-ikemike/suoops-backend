# Data Retention Policy

**Owner:** Data Protection Officer (privacy@suoops.com)
**Applies to:** SuoOps platform (invoicing, payments, storefront, courier delivery)
**Last reviewed:** 2026-07-14 · **Review cycle:** annual (or on material change)

> This policy states how long SuoOps keeps each category of personal data, why,
> and how it is deleted or archived. It exists to satisfy the NDPA 2023 storage‑
> limitation principle and Nigerian record‑keeping law (tax/financial records).
> It is not legal advice; the appointed DPCO reviews it at the annual audit.

## 1. Principles
- **Storage limitation** — personal data is kept only as long as needed for the
  purpose it was collected, or as required by law.
- **Legal holds override deletion** — where a financial/tax record, an open
  dispute, or a regulatory obligation requires retention, data is retained until
  that obligation ends (see §4).
- **Minimisation** — we do not retain data we no longer need; contact details are
  masked from counterparties where the purpose does not require exposure.

## 2. Categories of personal data & retention periods

| Category | Examples (SuoOps fields) | Retention | Basis |
|---|---|---|---|
| **Financial / transaction records** | Invoices, receipts, storefront orders, wallet ledger, payout & escrow records, bank account name/number | **6 years** after the transaction (then archived/anonymised) | Nigerian tax & company law record‑keeping; contract |
| **Account (seller) data** | Name, phone, email, business name, logo, storefront settings, bank details | Life of the account **+ 90 days** after deletion (minus any legal hold) | Contract; legitimate interest |
| **Customer (buyer) data** | Name, phone, email captured on invoices/orders | Tied to the related invoice/order → **6 years** (financial record) | Contract; legal obligation |
| **Delivery / location data** | GPS coordinates, delivery address, derived state | **24 months** from the order (then deleted) | Contract (delivery + buyer‑protection window) |
| **Order‑chat & dispute evidence** | Order messages (`body_raw`), dispatch/delivery proof photos | **24 months** from order close (dispute evidence) | Legitimate interest (fraud/dispute) |
| **Authentication secrets** | OTP codes | **10 minutes** (TTL), then auto‑deleted from Redis | Security |
| **Revoked auth tokens** | Token blocklist entries | Until natural token expiry (~14 days) | Security |
| **Fraud / trust signals** | Signup IP, device fingerprint, user‑agent, risk score, circumvention flags | **24 months** from last activity | Legitimate interest (fraud prevention) |
| **Audit & security logs** | `audit.py` events, access logs | **18 months** | Security, accountability |
| **Object storage (S3) archival** | Invoice/receipt PDFs, receipt images, tax reports | PDFs → Glacier after **90 days**; receipt images after **180 days**; tax archives after **365 days**; deleted per the schedules above | Cost + record‑keeping |
| **Marketing/engagement** | Email/WhatsApp opt‑in status | Until opt‑out or account deletion | Consent |

## 3. Deletion & anonymisation
- **Account deletion** is available in‑app (self‑service) and via
  privacy@suoops.com. It is executed by `account_deletion_service`, which **blocks
  deletion while there is held/disputed escrow** (funds/obligations outstanding)
  and otherwise removes/anonymises account data after the 90‑day window.
- **Financial records are not hard‑deleted** before the 6‑year period; instead
  personal identifiers may be redacted/anonymised while the transaction record is
  retained for tax/audit.
- **Automated expiry**: OTPs, tokens and S3 lifecycle transitions expire
  automatically; periodic jobs purge data past its retention window.

## 4. Legal holds
Retention is extended beyond the periods above where required by: an open dispute
or chargeback, a tax/regulatory investigation, a law‑enforcement request, or a
pending legal claim. The hold ends when the matter is resolved.

## 5. Responsibilities
- **DPO** owns this policy, approves retention changes, and evidences compliance
  at the annual audit.
- **Engineering** implements automated expiry/purge jobs and honours deletion
  requests within statutory timelines.
