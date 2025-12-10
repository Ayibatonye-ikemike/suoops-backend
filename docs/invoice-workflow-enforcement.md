# Invoice Payment Workflow Enforcement

## Overview

Implemented strict payment confirmation workflow to ensure proper verification of customer payments before marking invoices as paid. This prevents premature inventory deduction and ensures business owners verify bank transfers.

## Workflow

```
pending → awaiting_confirmation → paid
         ↘                       ↗
          -----→ failed ←--------
```

### Status Transitions

1. **pending**: Initial state when invoice is created
   - Customer receives payment link
   - Can transition to: `awaiting_confirmation` or `failed`
   - **Cannot** transition directly to `paid`

2. **awaiting_confirmation**: Customer confirms they've sent payment
   - Business owner must verify bank transfer
   - Can transition to: `paid` or `failed`
   - **Cannot** go back to `pending`

3. **paid**: Payment verified by business owner
   - Receipt automatically sent to customer
   - Inventory deducted from stock
   - **Terminal state** - no further transitions allowed

4. **failed**: Invoice closed without payment
   - **Terminal state** - no further transitions allowed

## Implementation

### Backend Changes

**File**: `/app/services/invoice_components/status.py`

Added validation in `update_status()` method:

```python
# Enforce workflow: can only mark paid if previous status was awaiting_confirmation
if status == "paid" and previous_status != "awaiting_confirmation":
    raise ValueError(
        "Cannot mark invoice as paid directly. "
        "Customer must first confirm payment (status: awaiting_confirmation), "
        "then you can verify and mark as paid."
    )
```

This ensures:
- Backend rejects direct `pending → paid` transitions
- Returns 422 error with clear message about workflow
- Protects inventory from premature deduction

### Frontend Changes

**File**: `/src/features/invoices/invoice-detail.tsx`

Added `getAllowedStatusOptions()` helper:

```typescript
function getAllowedStatusOptions(currentStatus: string) {
  // From pending: can go to awaiting_confirmation or failed (but not directly to paid)
  if (currentStatus === "pending") {
    return allOptions.filter((opt) => opt.value !== "paid");
  }

  // From awaiting_confirmation: can go to paid or failed
  if (currentStatus === "awaiting_confirmation") {
    return allOptions.filter((opt) => opt.value !== "pending");
  }

  // Terminal states: no transitions allowed
  if (currentStatus === "paid" || currentStatus === "failed") {
    return allOptions.filter((opt) => opt.value === currentStatus);
  }
}
```

This ensures:
- Status dropdown only shows valid next states
- Users are guided through proper workflow
- Terminal states locked to prevent accidental changes

**File**: `/src/features/invoices/status-map.ts`

Updated help text to clarify workflow:

```typescript
export const invoiceStatusHelpText: Record<string, string> = {
  pending: "Customer must confirm they've sent payment before you can mark as paid. Share the payment link below.",
  awaiting_confirmation: "Customer confirmed payment. Check your bank, then mark as paid to send receipt and deduct inventory.",
  paid: "Payment verified and receipt sent. Inventory has been deducted.",
  failed: "Use this if the invoice will not be collected.",
};
```

## Benefits

1. **Payment Verification**: Forces business owners to verify bank transfers before marking as paid
2. **Inventory Protection**: Prevents stock deduction until payment is confirmed by both parties
3. **Clear Communication**: Explicit workflow messages guide users through proper steps
4. **Audit Trail**: Status progression creates clear payment confirmation timeline
5. **Error Prevention**: Terminal states locked to prevent accidental status changes

## User Experience

### For Business Owners

1. Create invoice with status `pending`
2. Share payment link with customer
3. Wait for customer to confirm payment (status changes to `awaiting_confirmation`)
4. Verify bank transfer received
5. Mark as `paid` → triggers receipt email + inventory deduction

### For Customers

1. Receive payment link
2. Make bank transfer
3. Click "I've sent the transfer" button on payment page
4. Invoice status changes to `awaiting_confirmation`
5. Receive receipt email once business owner verifies and marks as `paid`

## Testing

### Manual Test Cases

1. **Test direct paid transition (should fail)**:
   - Create invoice with status `pending`
   - Try to update status directly to `paid`
   - Expected: 422 error with workflow message

2. **Test proper workflow (should succeed)**:
   - Create invoice with status `pending`
   - Update status to `awaiting_confirmation`
   - Update status to `paid`
   - Expected: Success, receipt sent, inventory deducted

3. **Test terminal state lock**:
   - Mark invoice as `paid`
   - Try to change status to any other value
   - Expected: Only `paid` option shown in dropdown

## Deployment

- **Backend**: Heroku v290 (commit 4c0eb86c)
- **Frontend**: Vercel (commit c2b12fe)
- **Status**: ✅ Deployed to production

## Related Features

- Invoice creator tracking (`created_by_user_id`)
- Inventory deduction on payment
- Auto-calculation of invoice totals
- Team member inventory access

## Future Enhancements

- Add status change notifications (email/SMS)
- Implement payment deadline reminders
- Add payment proof upload feature
- Track status change history with timestamps
