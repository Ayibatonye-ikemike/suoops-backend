# Tax & Fiscalization System - NRS 2026 Compliance

SuoOps tax compliance implementation for Nigeria's 2026 Tax Reform Acts.

## Overview

This implementation adds comprehensive tax and fiscalization features to SuoOps, positioning it as Nigeria's first MSME-ready tax-compliant invoice platform ahead of the January 1, 2026 deadline.

## Features

### 1. Business Tax Classification
- **Automatic classification** based on NRS 2026 thresholds
- Small business: Turnover ≤ ₦100M AND Assets ≤ ₦250M (Tax exempt)
- Medium/Large: Above thresholds (Taxable)
- Real-time tax rate calculation

### 2. VAT Management
- **7.5% standard VAT** calculation
- **Zero-rated detection** for medical, education, basic food
- **Exempt categories** for financial services
- **Export handling** (0% VAT)
- Monthly VAT returns generation

### 3. Invoice Fiscalization
- **Unique fiscal codes** (Format: NGR-YYYYMMDD-USERID-INVOICEID-HASH)
- **Digital signatures** using SHA256
- **QR codes** with embedded fiscal data
- **NRS transmission** (when API configured)

### 4. Compliance Tracking
- Business size classification
- VAT registration status
- Monthly VAT returns
- Compliance alerts

## Architecture

### Following Best Practices
✅ **Single Responsibility Principle (SRP)**: Each class has one job
✅ **DRY (Don't Repeat Yourself)**: Reusable components
✅ **OOP**: Proper encapsulation and inheritance
✅ **< 400 LOC per file**: Maintainable code size

### File Structure

```
app/
├── models/
│   ├── models.py                      # Updated with VAT fields
│   └── tax_models.py                  # Tax-specific models (190 LOC)
├── services/
│   ├── fiscalization_service.py       # Fiscalization logic (380 LOC)
│   ├── vat_service.py                 # VAT calculations (240 LOC)
│   └── tax_service.py                 # Tax profiles (175 LOC)
├── api/
│   ├── routes_tax.py                  # Tax endpoints (220 LOC)
│   └── main.py                        # Updated routes
└── core/
    └── config.py                      # NRS config added

alembic/versions/
└── 0005_add_tax_fiscalization.py      # Migration (130 LOC)
```

### Component Breakdown

#### Tax Models (`tax_models.py`)
- `TaxProfile`: Business classification, TIN, VAT registration
- `FiscalInvoice`: Fiscal codes, signatures, QR codes
- `VATReturn`: Monthly VAT returns
- `BusinessSize`, `VATCategory`: Enums

#### Fiscalization Service (`fiscalization_service.py`)
- `VATCalculator`: VAT calculation logic (SRP)
- `FiscalCodeGenerator`: Unique code generation (SRP)
- `QRCodeGenerator`: QR code creation (SRP)
- `NRSTransmitter`: API communication (SRP)
- `FiscalizationService`: Orchestrates above components

#### VAT Service (`vat_service.py`)
- `VATCalculationService`: Period calculations (SRP)
- `ComplianceChecker`: Status checking (SRP)
- `VATService`: Orchestrates VAT operations

#### Tax Service (`tax_service.py`)
- `BusinessClassifier`: Size classification (SRP)
- `TaxProfileService`: Profile management

## API Endpoints

### Tax Profile Management

```bash
# Get tax profile
GET /tax/profile
Authorization: Bearer {token}

Response:
{
  "business_size": "small",
  "is_small_business": true,
  "tax_rates": {
    "CIT": 0,
    "CGT": 0,
    "DEV_LEVY": 0,
    "VAT": 7.5
  },
  "classification": {...},
  "registration": {...}
}

# Update tax profile
POST /tax/profile
{
  "annual_turnover": 50000000,
  "fixed_assets": 100000000,
  "tin": "12345678-0001",
  "vat_registered": true
}
```

### VAT Operations

```bash
# Calculate VAT
GET /tax/vat/calculate?amount=10000&category=standard

Response:
{
  "subtotal": 9302.33,
  "vat_rate": 7.5,
  "vat_amount": 697.67,
  "total": 10000,
  "category": "standard"
}

# Get VAT summary
GET /tax/vat/summary

Response:
{
  "registered": true,
  "current_month": {
    "output_vat": 15000,
    "net_vat": 15000,
    ...
  },
  "compliance_status": "compliant"
}

# Generate VAT return
POST /tax/vat/return?year=2026&month=1

Response:
{
  "tax_period": "2026-01",
  "output_vat": 15000,
  "input_vat": 0,
  "net_vat": 15000,
  "status": "draft"
}
```

### Invoice Fiscalization

```bash
# Fiscalize an invoice
POST /tax/invoice/{invoice_id}/fiscalize

Response:
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
  "nrs_status": "validated"
}
```

## Database Schema

### tax_profiles
- Business classification
- TIN, VAT registration
- NRS credentials

### fiscal_invoices
- Fiscal code (unique)
- Digital signature
- QR code (base64)
- VAT breakdown
- NRS transmission status

### vat_returns
- Monthly period (YYYY-MM)
- Output/input VAT
- Zero-rated sales
- Submission status

### invoice (updated)
- vat_rate
- vat_amount
- vat_category
- is_fiscalized
- fiscal_code

## Setup

### 1. Run Migration

```bash
alembic upgrade head
```

### 2. Environment Variables

Add to `.env`:

```bash
# NRS Integration (will be provided after registration)
NRS_API_URL=https://api.nrs.gov.ng/v1
NRS_API_KEY=your_nrs_api_key
NRS_MERCHANT_ID=your_merchant_id
```

### 3. Test the API

```bash
python test_tax_api.py
```

## Usage Examples

### Small Business Flow

```python
# 1. Set up tax profile
POST /tax/profile
{
  "annual_turnover": 50000000,    # ₦50M
  "fixed_assets": 100000000,       # ₦100M
  "tin": "12345678-0001"
}
# → Automatically classified as "small" (tax exempt)

# 2. Create invoice (auto VAT calculation)
POST /invoices
{
  "customer_name": "John Doe",
  "amount": 10000
}
# → VAT automatically calculated: ₦697.67

# 3. Fiscalize invoice
POST /tax/invoice/123/fiscalize
# → Gets fiscal code, QR code, transmitted to NRS

# 4. Generate monthly VAT return
POST /tax/vat/return?year=2026&month=1
# → Aggregates all invoices for January 2026
```

### VAT Category Detection

```python
from app.services.fiscalization_service import VATCalculator

# Auto-detect from description
category = VATCalculator.detect_category("Medical supplies")
# → "zero_rated" (0% VAT)

category = VATCalculator.detect_category("School textbooks")
# → "zero_rated" (0% VAT)

category = VATCalculator.detect_category("Hair products")
# → "standard" (7.5% VAT)
```

## NRS Integration

### Registration Process

1. **Submit application** to NRS with:
   - Technical capabilities document
   - API documentation
   - SLA template
   - Infrastructure details

2. **Receive credentials**:
   - NRS API URL
   - API Key
   - Merchant ID

3. **Configure environment**:
   ```bash
   NRS_API_URL=https://api.nrs.gov.ng/v1
   NRS_API_KEY=your_key
   NRS_MERCHANT_ID=your_id
   ```

4. **Test transmission**:
   - Fiscalize test invoice
   - Verify NRS response
   - Check validation status

### NRS Payload Format

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
    "items": [...]
  }
}
```

## Testing

### Unit Tests

```bash
# Test VAT calculations
pytest tests/test_vat_calculator.py

# Test fiscalization
pytest tests/test_fiscalization.py

# Test business classification
pytest tests/test_tax_service.py
```

### Integration Tests

```bash
# Full flow test
python test_tax_api.py
```

## Tax Benefits by Business Size

### Small Business (≤₦100M turnover, ≤₦250M assets)
- ✅ Company Income Tax: **EXEMPT** (₦0)
- ✅ Capital Gains Tax: **EXEMPT** (₦0)
- ✅ Development Levy: **EXEMPT** (₦0)
- ⚠️ VAT: **7.5%** (still applicable)
- 💰 **Annual savings: ₦2M-10M** depending on profits

### Medium/Large Business
- Company Income Tax: **25%** on profits
- Capital Gains Tax: **30%** on capital gains
- Development Levy: **4%** on assessable profits
- VAT: **7.5%** standard rate

## Compliance Checklist

- [ ] Business classified correctly
- [ ] TIN registered
- [ ] VAT registration (if applicable)
- [ ] Monthly VAT returns generated
- [ ] Invoices fiscalized
- [ ] NRS credentials configured
- [ ] Test transmission successful
- [ ] QR codes displaying on invoices
- [ ] Compliance dashboard monitored

## Roadmap

### Q4 2024
- [x] Core tax models
- [x] VAT calculation engine
- [x] Fiscalization service
- [x] API endpoints
- [ ] Frontend integration

### Q1 2025
- [ ] NRS API integration
- [ ] Advanced VAT features
- [ ] Expense tracking (input VAT)
- [ ] Tax optimization suggestions

### Q2 2025
- [ ] Multi-entity support
- [ ] White-label fiscalization
- [ ] Advanced analytics
- [ ] ISO 27001 certification

## Support

- **Documentation**: `/docs/tax-compliance.md`
- **API Docs**: `GET /docs` (includes tax endpoints)
- **Support**: support@suoops.com

## License

Proprietary - SuoOps Platform
