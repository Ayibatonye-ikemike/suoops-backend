# Nigerian Tax Law Compliance - 2026 Updates

## Critical Issues Identified

### ❌ Current Implementation Issues

1. **Wrong Small Business Threshold**
   - Current: ₦100,000,000 (₦100M)
   - Correct: ₦50,000,000 (₦50M)
   - Impact: Businesses between ₦50M-₦100M wrongly classified as small

2. **Missing Profit vs Revenue Distinction**
   - Current: "Assessable Profit" = Total Revenue (no expense deduction)
   - Correct: Profit = Revenue - Allowable Expenses
   - Impact: Tax calculated on gross sales instead of net profit

3. **Wrong Tax Type for Small Businesses**
   - Current: Company Income Tax (CIT) framework
   - Correct: Personal Income Tax (PIT) with progressive rates
   - Impact: Wrong tax calculation for sole proprietors/freelancers

4. **Development Levy Calculation**
   - Current: 4% levy for businesses > ₦100M
   - Correct: Not mentioned in informal/micro business tax laws
   - Impact: May be incorrectly applying corporate tax rules

### ✅ Correct 2026 Tax Law (Effective Jan 1, 2026)

#### Small Business Exemption
```
Annual Turnover ≤ ₦50,000,000 → EXEMPT from Company Income Tax (CIT)
```

#### Personal Income Tax (PIT) Progressive Rates
```
First ₦800,000:      0%    (Tax-free)
Next ₦2,200,000:    15%    (₦800K - ₦3M)
Next ₦9,000,000:    18%    (₦3M - ₦12M)
Next ₦13,000,000:   21%    (₦12M - ₦25M)
Next ₦25,000,000:   23%    (₦25M - ₦50M)
Above ₦50,000,000:  25%    (₦50M+)
```

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

## Required Changes

### Phase 1: Update Thresholds (Immediate)

**Files to Update:**
1. `app/services/tax_service.py`
   - Change `SMALL_BUSINESS_TURNOVER_LIMIT` from ₦100M to ₦50M
   - Update `BusinessClassifier.SMALL_TURNOVER_THRESHOLD`

2. `app/models/tax_models.py`
   - Update tax rate constants

3. `app/services/tax_profile_service.py`
   - Update threshold constants

**Migration:**
```sql
-- Reclassify businesses between ₦50M-₦100M
UPDATE tax_profiles
SET business_size = 'medium'
WHERE annual_turnover > 50000000 
  AND annual_turnover <= 100000000
  AND business_size = 'small';
```

### Phase 2: Add Expense Tracking (Critical)

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

## Implementation Priority

### 🔴 Critical (Do Now)
1. Update threshold from ₦100M → ₦50M
2. Add UI warning about revenue vs profit
3. Rename misleading labels

### 🟡 High Priority (Next Sprint)
1. Add expense tracking model & API
2. Update profit calculation to include expenses
3. Implement PIT progressive tax calculator

### 🟢 Medium Priority (Future)
1. Add expense categories and receipt uploads
2. Implement presumptive taxation
3. Add tax planning tools

## Testing Checklist

- [ ] Businesses at ₦49M classified as small
- [ ] Businesses at ₦51M classified as medium
- [ ] PIT calculated correctly for all brackets
- [ ] Expense deduction reduces taxable profit
- [ ] UI shows clear revenue vs profit distinction
- [ ] Tax reports accurate for 2026 law

## References

- Nigeria Tax Laws 2026 (Effective Jan 1, 2026)
- FIRS Guidelines for Informal/Micro Businesses
- Personal Income Tax (PIT) Progressive Rates
- Small Business Exemption Rules

## Notes

**Why Current Implementation is Wrong:**
1. We're using **Company Income Tax (CIT)** framework for sole proprietors
2. CIT applies to registered companies, not freelancers/influencers
3. Informal businesses pay **Personal Income Tax (PIT)**
4. PIT is progressive (0%-25%), not flat rate

**Impact:**
- Users between ₦50M-₦100M getting wrong tax calculations
- No expense tracking means overpaying taxes
- Wrong tax type (CIT vs PIT) for target market
