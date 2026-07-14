# Data Protection Impact Assessment (DPIA)

**System:** SuoOps — invoicing, payments/escrow, buyer‑protected storefront & courier delivery
**Owner:** Data Protection Officer (dpo@suoops.com)
**Last reviewed:** 2026-07-14 · **Review cycle:** annual + on material change to processing

> A DPIA is required because SuoOps carries out high‑risk processing under the
> NDPA 2023: large‑scale processing of financial and personal data, systematic
> monitoring for fraud, and cross‑border transfers. This is not legal advice; the
> appointed DPCO reviews it at the annual audit.

## 1. Description of the processing
- **Nature:** collection, storage, use, sharing and cross‑border transfer of
  personal data to run an invoicing + payments + commerce + delivery platform.
- **Scope:** ~1,000–5,000 data subjects processed per 6 months (sellers and their
  customers/buyers), growing.
- **Context:** Nigerian SMEs (sellers) and their customers (buyers). Money moves
  through the platform (wallet, storefront escrow, payouts).
- **Purposes:** create/deliver invoices & receipts; process online payments and
  escrow; enable storefront orders and courier delivery; authenticate users
  (OTP); prevent fraud and resolve disputes; tax reporting; service comms.

## 2. Data & data subjects
| Data subjects | Personal data categories |
|---|---|
| Sellers (registered users) | Name, phone, email, business name, **bank account name/number**, logo, storefront settings |
| Buyers (customers) | Name, phone, email, **delivery address & GPS**, order/invoice history |
| Both | IP address, device fingerprint, user‑agent (fraud prevention); order‑chat messages |

**Special note:** financial data (bank details, transactions) is high‑harm if
breached. SuoOps does **not** process NDPA special categories (health, biometric,
genetic, ethnic, religious, political, sexual).

## 3. Data flows & recipients (processors)
- **Payments:** Paystack, Flutterwave (Nigeria).
- **Delivery:** Shipbubble / GIG Logistics (Nigeria) — buyer name, phone, address.
- **Infrastructure (cross‑border, USA):** Render (hosting), AWS S3 (files),
  Vercel (frontend), Sentry (error monitoring).
- **Messaging:** Meta/WhatsApp, Brevo, Amazon SES (email/SMS).
- **Geocoding/maps:** Mapbox (address/state derivation).

## 4. Necessity & proportionality
- Each data element is tied to a purpose (see §1) — e.g. GPS is used only to derive
  the buyer‑protection state window and to arrange delivery; bank details only for
  payouts; IP/device only for fraud prevention.
- **Data minimisation** is applied: the buyer's phone/address is **masked from the
  seller** on courier orders (courier handles contact); unnecessary invoice fields
  are hidden; order‑chat masks/blocks contact & account leaks.
- Lawful bases: performance of contract (invoicing, payments, delivery), legal
  obligation (tax/financial records), and legitimate interests (fraud prevention),
  balanced against data‑subject rights.

## 5. Risks to data subjects & mitigations
| Risk | Likelihood | Impact | Mitigations |
|---|---|---|---|
| **Financial‑data exposure** (bank details, transactions) | Low | High | TLS + encryption at rest; bank numbers masked in admin views; least‑privilege access; audit logging |
| **Account takeover** | Low | High | OTP auth (constant‑time compare, attempt caps, TTL), token revocation/blocklist, CSRF, rate limiting |
| **Buyer contact/data misuse by seller (disintermediation)** | Medium | Medium | Buyer phone/address masked from seller on courier orders; order‑chat masks/blocks contact, account & spelled/split numbers; circumvention flags |
| **Cross‑border transfer to weaker regimes** | Medium | Medium | Reputable processors with security programs; DPAs; encryption in transit/at rest; document transfer countries in NDPC filing |
| **Unauthorised admin access** | Low | High | Admin IP allow‑list, RBAC + super‑admin gating on money moves, step‑up OTP for high‑value actions, audit trail |
| **Excessive retention** | Low | Medium | Data Retention Policy with defined periods + automated expiry; deletion honours legal holds |
| **Fraud / collusion harming buyers** | Medium | Medium | Escrow hold + buyer‑protection window, dispute review, duplicate‑account & self‑dealing detection |
| **Breach without timely notice** | Low | High | Incident Response Plan with NDPC 72‑hour notification + data‑subject notice |

## 6. Measures summary (technical & organisational)
Firewalls/WAF (Cloudflare), encryption (TLS + at rest), audit logging, RBAC +
OTP + step‑up auth, data minimisation/masking, DLP (leak masking), backups &
recovery, cookie consent, published data‑subject rights + grievance channel,
DPO designation, Data Retention Policy, Incident Response Plan, vendor DPAs.

## 7. Residual risk & sign‑off
With the measures above, residual risk is assessed as **Medium** (reduced from an
inherent High driven by financial data + fund movement). Processing may proceed
subject to: (a) maintaining vendor DPAs, (b) executing automated retention/purge,
(c) reviewing this DPIA annually and after any material change, and (d) the DPCO's
review at the annual compliance audit.

**DPO sign‑off:** __________________________  **Date:** ____________
