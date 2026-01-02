# Nigerian Tax Law Compliance - NTA 2025 (Effective January 1, 2026)

## ✅ Implementation Updated for NTA 2025

This document reflects the Nigeria Tax Act 2025 (NTA 2025) which came into effect on January 1, 2026.

### Key Tax Thresholds

| Tax Type | Threshold | Rate |
|----------|-----------|------|
| **VAT Exemption** | ≤₦25,000,000 (₦25M) | 0% (exempt) |
| **CIT - Small Company** | ≤₦100,000,000 (₦100M) | 0% (exempt) |
| **CIT - Medium Company** | ₦100M - ₦250M | 20% |
| **CIT - Large Company** | >₦250,000,000 (₦250M) | 30% |

### Current Implementation Status

1. **Small Business Threshold** ✅
   - Current: ₦100,000,000 (₦100M)
   - Correct per NTA 2025: ₦100,000,000 (₦100M)

2. **VAT Threshold** ✅
   - Current: ₦25,000,000 (₦25M)
   - Correct per NTA 2025: ₦25,000,000 (₦25M) (unchanged)

3. **CIT Rates** ✅
   - Small: 0% (exempt)
   - Medium: 20%
   - Large: 30%

### Personal Income Tax (PIT) Progressive Rates (NTA 2025)
```
Annual Turnover ≤ ₦50,000,000 → EXEMPT from Company Income Tax (CIT)
```

These PIT rates apply to freelancers and sole proprietors (not registered companies).

#### Profit Calculation
```
Taxable Profit = Total Income - Allowable Expenses - Deductions

Allowable Expenses:
- Rent
- Supplies/Equipment
- Professional fees
- Marketing costs
- Data/Internet
- Other legitimate business expenses
```

#### Tax Obligations
1. **Self-Assessment**: Businesses must self-declare income
2. **Record-Keeping**: Maintain accurate records of income & expenses
3. **Presumptive Taxation**: If no records, tax authority estimates income

## Implementation Status

### ✅ Completed Updates

**Files Updated:**
1. `app/services/tax_service.py`
   - ✅ `SMALL_BUSINESS_TURNOVER_LIMIT` = ₦100M
   - ✅ `BusinessClassifier.SMALL_TURNOVER_THRESHOLD` = ₦100M
   - ✅ `MEDIUM_TURNOVER_THRESHOLD` = ₦250M

2. `app/models/tax_models.py`
   - ✅ BusinessSize enum updated for NTA 2025
   - ✅ Tax rates: Small 0%, Medium 20%, Large 30%

3. `app/services/tax_profile_service.py`
   - ✅ Threshold constants updated

4. `support-suoops/app/articles/tax/exemptions/page.tsx`
   - ✅ Complete rewrite with NTA 2025 thresholds

5. `src/config/tax.ts`
   - ✅ All NTA 2025 thresholds and rates

6. `src/components/landing/features.tsx`
   - ✅ Updated ₦100M CIT exemption

### 🔄 Future Enhancements

**Phase 2: Add Expense Tracking**

**New Models:**
```python
class Expense(Base):
    """Business expenses for profit calculation"""
    id: int
    user_id: int
    amount: Decimal
    category: str  # rent, supplies, marketing, etc.
    description: str
    date: date
    receipt_url: str | None
    created_at: datetime
```

**Update Profit Calculation:**
```python
def compute_actual_profit(
    user_id: int,
    start_date: date,
    end_date: date,
) -> Decimal:
    """
    Compute ACTUAL profit (Revenue - Expenses)
    """
    revenue = get_total_revenue(user_id, start_date, end_date)
    expenses = get_total_expenses(user_id, start_date, end_date)
    return revenue - expenses
```

### Phase 3: Implement PIT Progressive Tax

**New Service:**
```python
class PersonalIncomeTaxCalculator:
    """
    Calculate PIT using 2026 progressive rates
    """
    TAX_BRACKETS = [
        (800_000, 0.00),      # First ₦800K: 0%
        (2_200_000, 0.15),    # Next ₦2.2M: 15%
        (9_000_000, 0.18),    # Next ₦9M: 18%
        (13_000_000, 0.21),   # Next ₦13M: 21%
        (25_000_000, 0.23),   # Next ₦25M: 23%
        (float('inf'), 0.25), # Above ₦50M: 25%
    ]
    
    def calculate_pit(self, taxable_income: Decimal) -> Decimal:
        """Calculate PIT using progressive brackets"""
        # Implementation
```

### Phase 4: Update UI Labels

**Frontend Changes:**
```tsx
// Change misleading labels
"Profit" → "Revenue (Sales)"  // Until expenses are tracked
"Assessable Profit" → "Total Revenue"
"Development Levy" → "Estimated Tax (PIT)"  // After PIT implementation

// Add warnings
"⚠️ This shows revenue only. Track expenses to calculate actual profit."
"⚠️ Tax calculation will be updated for 2026 law compliance."
```

## Future Enhancements

### 🟡 High Priority (Next Sprint)
1. Add expense tracking model & API
2. Update profit calculation to include expenses
3. Implement PIT progressive tax calculator for sole proprietors

### 🟢 Medium Priority (Future)
1. Add expense categories and receipt uploads
2. Implement presumptive taxation
3. Add tax planning tools

## Testing Checklist

- [x] Businesses at ₦99M classified as small (CIT exempt)
- [x] Businesses at ₦101M classified as medium (20% CIT)
- [x] Businesses at ₦251M classified as large (30% CIT)
- [ ] PIT calculated correctly for all brackets (future)
- [ ] Expense deduction reduces taxable profit (future)
- [x] UI shows correct ₦100M CIT threshold
- [x] Support articles updated for NTA 2025

## References

- Nigeria Tax Act 2025 (NTA 2025) - Effective Jan 1, 2026
- Federal Inland Revenue Service (FIRS) Guidelines
- Personal Income Tax (PIT) Progressive Rates
- Small Business CIT Exemption Rules

## Notes

**Current Implementation:**
- Supports both CIT (registered companies) and PIT (individuals/freelancers)
- CIT exemption for turnover ≤₦100M (NTA 2025)
- VAT exemption for turnover ≤₦25M (unchanged)
- Development levy at 4% for non-exempt businesses

**Future Improvements:**
- Add expense tracking for accurate profit calculation
- Implement full PIT progressive calculator
- Add tax planning recommendations
