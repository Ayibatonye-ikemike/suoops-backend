# Tax & Fiscalization System – FIRS Readiness (NTA 2025)

> DISCLAIMER: This document describes provisional fiscalization capabilities. External transmission to Federal Inland Revenue Service (FIRS) systems is DISABLED until accreditation is granted and live credentials are issued. All references to gateway interaction are forward-looking roadmap items, not active production features.

SuoOps tax compliance foundation for Nigeria Tax Act 2025 (NTA 2025) effective January 1, 2026, and emerging e-invoicing/fiscalization standards.

## Overview

This module provides core tax modeling, VAT calculation, and provisional (locally generated) fiscal artifacts (codes, signatures, QR). It is designed for MSME readiness while deferring external validation until accreditation. No claims of live regulatory integration are made.

## Features

### 1. Business Tax Classification (NTA 2025)
- Automatic classification based on configurable thresholds
- **Small business:** Turnover ≤ ₦100M AND Assets ≤ ₦250M (CIT exempt - 0%)
- **Medium business:** Turnover ₦100M-₦250M (CIT 20%)
- **Large business:** Turnover > ₦250M (CIT 30%)
- VAT registration required separately when turnover > ₦25M
- Dynamic tax rate profile surface

### 2. VAT Management
- 7.5% standard VAT computation
- Zero-rated detection (medical, education, basic food)
- Exempt category handling (financial services, etc.)
- Export handling (0%)
- Monthly VAT return aggregation (draft status)

### 3. Invoice Fiscalization (Provisional)
- Deterministic fiscal code format: `NGR-YYYYMMDD-USERID-INVOICEID-HASH`
- SHA256 signature (local integrity only)
- QR code embedding fiscal metadata
- External transmission: gated by `FISCALIZATION_ACCREDITED` flag (defaults False)

### 4. Compliance Tracking
- Business size classification snapshot
- VAT registration status
- Draft VAT returns
- Readiness / accreditation gating indicators

## Architecture

### Principles
✅ SRP (each helper class isolated)
✅ DRY reuse of VAT computation helpers
✅ Clear service orchestration layer (`FiscalizationService`)
✅ Separation between generation vs. external transmission (placeholder)

### Key Files (illustrative subset)
```
app/
  models/tax_models.py          # TaxProfile, FiscalInvoice, VATReturn
  services/fiscalization_service.py  # Orchestrates provisional artifacts
  api/routes_tax.py             # Endpoints exposing tax/fiscalization
  core/config.py                # FISCALIZATION_ACCREDITED flag
alembic/versions/               # Schema migrations
```

### Components
- VATCalculator: Subtotal/VAT breakdown
- FiscalCodeGenerator: Code assembly
- QRCodeGenerator: PNG (base64) generation
- FiscalTransmitter (placeholder): Deferred external gateway adapter (inactive until accreditation)
- FiscalizationService: Orchestrates end-to-end local fiscalization

## API Endpoints (Selected)

### Tax Profile
```bash
GET /tax/profile
POST /tax/profile
```
Response excerpt:
```json
{
  "business_size": "small",
  "tax_rates": {"CIT": 0, "CGT": 0, "DEV_LEVY": 0, "VAT": 7.5},
  "classification": {...},
  "registration": {...}
}
```

### VAT Operations
```bash
GET /tax/vat/calculate?amount=10000&category=standard
GET /tax/vat/summary
POST /tax/vat/return?year=2026&month=1
```
Example calculation response:
```json
{
  "subtotal": 9302.33,
  "vat_rate": 7.5,
  "vat_amount": 697.67,
  "total": 10000,
  "category": "standard"
}
```

### Invoice Fiscalization (Provisional)
```bash
POST /tax/invoice/{invoice_id}/fiscalize
```
Example response:
```json
{
  "fiscal_code": "NGR-20260115-00123-00004567-A1B2C3D4",
  "fiscal_signature": "a1b2c3...",
  "qr_code": "data:image/png;base64,...",
  "vat_breakdown": {
    "subtotal": 9302.33,
    "vat_rate": 7.5,
    "vat_amount": 697.67,
    "total": 10000
  },
  "fiscalization_status": "pending_external"
}
```

## Database Schema (Conceptual)

### tax_profiles
- Classification metadata
- TIN, VAT registration flag
- Accreditation readiness flag (if needed)

### fiscal_invoices
- Fiscal code (unique)
- Local signature
- QR code (base64)
- VAT breakdown snapshot
- Provisional status field

### vat_returns
- Period key (YYYY-MM)
- Output VAT, input VAT (future expansion)
- Zero-rated totals
- Draft/Filed (post-accreditation) state

### invoice (extended)
- vat_rate, vat_amount, vat_category
- is_fiscalized, fiscal_code

## Setup

### Migration
```bash
alembic upgrade head
```

### Environment Variables (Placeholders)
```bash
# External gateway placeholders (inactive until accreditation)
FISCALIZATION_ACCREDITED=false
FIRS_API_URL=
FIRS_API_KEY=
```

## Usage Examples (Abbreviated)

1. Create/Update Tax Profile → classification + tax rates.
2. Issue invoice → VAT auto-computed.
3. Fiscalize invoice → local artifacts generated (status: pending_external).
4. Generate monthly VAT return → draft summary for internal review.

## External Integration Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Local Generation | ✅ | Codes, signatures, QR, draft VAT returns |
| 2. Sandbox Gateway  | ⏳ | Acquire sandbox credentials, test payloads |
| 3. Accreditation     | ⏳ | Formal approval, production credentials |
| 4. Live Transmission | ⏳ | Real-time validation + status feedback |
| 5. Enhancements      | ⏳ | Retry queues, callback webhooks, metrics |

### Planned External Payload (Illustrative Only)
```json
{
  "fiscal_code": "NGR-20260115-00123-00004567-A1B2C3D4",
  "fiscal_signature": "a1b2c3d4...",
  "invoice_data": {
    "invoice_number": "INV-2026-001",
    "invoice_date": "2026-01-15T10:30:00Z",
    "customer_name": "John Doe",
    "subtotal": 9302.33,
    "vat_rate": 7.5,
    "vat_amount": 697.67,
    "total": 10000,
    "currency": "NGN",
    "items": []
  }
}
```

## Testing (Illustrative)
```bash
pytest tests/test_vat_calculator.py
pytest tests/test_fiscalization.py
pytest tests/test_tax_service.py
```

## Tax Considerations by Business Size (NTA 2025)

### Small Business (≤₦100M turnover & ≤₦250M assets)
- **CIT:** 0% (Exempt)
- **CGT:** Exempt
- **Development Levy:** Exempt
- **VAT:** Applicable if turnover exceeds ₦25M (separate threshold)

### Medium Business (₦100M-₦250M turnover)
- **CIT:** 20%
- **CGT:** Applicable
- **Development Levy:** 4%
- **VAT:** 7.5% standard rate

### Large Business (>₦250M turnover)
- **CIT:** 30%
- **CGT:** Applicable
- **Development Levy:** 4%
- **VAT:** 7.5% standard (with zero-rated/exempt nuances)

## Compliance Readiness Checklist
- [ ] Business classified correctly
- [ ] TIN recorded
- [ ] VAT registration status confirmed (if required)
- [ ] Invoices generating VAT breakdowns
- [ ] Provisional fiscalization artifacts present
- [ ] Accreditation flag OFF (until approval)
- [ ] Draft VAT returns generated
- [ ] Internal review dashboard monitored

## Roadmap

### Q4 2025
- [x] Core tax models
- [x] VAT calculation engine
- [x] Provisional fiscalization service
- [x] API endpoints
- [ ] Frontend compliance dashboard

### Q1 2026
- [ ] Accreditation application + sandbox creds
- [ ] Expense/input VAT tracking
- [ ] Transmission queue + retry metrics
- [ ] Threshold advisory UX

### Q2 2026
- [ ] Production gateway integration
- [ ] Real-time validation statuses
- [ ] Multi-entity support
- [ ] White-label fiscalization

### Q3 2026
- [ ] Advanced analytics & optimization hints
- [ ] ISO 27001 audit preparation
- [ ] Continuous compliance diff tooling

## Support
- Docs: `docs/tax-compliance.md`
- API Schema: OpenAPI under `/docs`
- Contact: support@suoops.com

## License
Proprietary – SuoOps Platform

---
This document will evolve as accreditation progresses; sections marked “Illustrative” are non-functional placeholders.
