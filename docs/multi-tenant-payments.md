# Manual Payment Architecture

## Overview

SuoPay now positions invoices as **bank-transfer workflows** instead of routing payments through Paystack. Each business keeps its own settlement account on file, customers pay them directly, and operators mark invoices as paid after confirming the transfer. Paystack remains in place **only for SuoPay subscription billing** (plan upgrades), so there is no payment gateway dependency in the invoice lifecycle.

### Why This Approach?
- **Regulatory clarity:** SuoPay never touches customer funds.
- **Operational control:** Businesses decide when funds are confirmed and can handle partial payments or reversals offline.
- **Lower complexity:** No need to manage multi-tenant Paystack keys, payment links, or per-business webhooks for invoices.
- **Native experience:** PDF invoices, WhatsApp confirmations, and receipts highlight the merchant’s own bank details.

## Implementation Highlights

1. **Database Fields** (Migration 0006)
   - `business_name`, `bank_name`, `account_number`, `account_name` captured on each user.
   - Optional Paystack keys are retained for future expansion but are not required for invoice payments.

2. **Invoice Service**
   - Generates invoice IDs and PDFs that surface the merchant’s bank instructions.
   - Tracks monthly invoice quotas per subscription plan and resets automatically each month.
   - Marks invoices as paid/failed manually; `invoice_service.update_status` sends WhatsApp receipts when configured.

3. **API Routes**
   - `POST /invoices` → creates invoices with line items, generates PDFs, increments usage counters.
   - `PATCH /invoices/{id}` → updates status (`pending`, `paid`, `failed`) based on manual confirmation.
   - No `/invoices/{id}/events` or `/invoices/payments/webhook` endpoints—statuses are controlled entirely by the business.

4. **WhatsApp Automation**
   - WhatsApp bot confirms invoice creation with customer-friendly copy and bank details.
   - When an invoice is marked as paid, SuoPay sends WhatsApp receipts (and optionally PDFs).

5. **Subscription Billing (Paystack)**
   - `/subscriptions/initialize` and `/subscriptions/verify` use Paystack for SuoPay’s own subscription revenue.
   - `/webhooks/paystack` now processes only `charge.success` events to upgrade plans; invoice-related webhooks were removed.

## Manual Payment Flow

```
Customer → Receives invoice/WhatsApp prompt with bank details
Customer → Transfers funds directly to merchant bank account
Merchant → Confirms funds → PATCH /invoices/{id} status=paid
SuoPay → Sends receipt (WhatsApp + PDF if available)
```

## Pending & Nice-to-Have Tasks

1. **Bank Details Management UI (MEDIUM)**
   - Dashboard settings page to capture `business_name`, `bank_name`, `account_number`, `account_name`.
   - Validation reminders (e.g. 10-digit account number) and guidance on what customers will see.

2. **Confirmation Aids (LOW)**
   - Add optional fields for reference numbers or payment notes when marking an invoice as paid.
   - Allow operators to upload proof-of-payment snapshots for internal auditing.

3. **Reconciliation Ideas (FUTURE)**
   - Optional integrations with bank statement providers (Mono, Okra, Stitch) for semi-automatic matching.
   - Optional Paystack invoice mode (opt-in) if a business explicitly wants gateway collection in addition to bank transfers.

## Testing Checklist

### Automated Tests
- `pytest tests/test_smoke.py::test_create_list_invoice_auth_flow` – verifies creation, listing, and quota checks.
- `pytest tests/test_smoke.py::test_invoice_detail_status_flow` – ensures manual status updates return 200 and reject invalid statuses.
- `pytest tests/test_smoke.py -k invoice_decimal_precision` – confirms decimal serialization still strips trailing zeros (regression coverage for finance calculations).

### Manual QA
1. Create an invoice via API or WhatsApp and confirm the PDF displays bank details.
2. Mark the invoice as `paid` via API; check logs/WhatsApp receipt delivery.
3. Attempt to mark the same invoice again—status should remain stable (idempotent manual update).
4. Update bank details and re-generate an invoice to confirm new details appear.

## FAQ

**Q: Do merchants still need Paystack keys?**  
No. Paystack is now used exclusively for SuoPay subscription billing (plan upgrades). Merchants only need to provide their settlement bank information.

**Q: Can I still send Paystack payment links to customers?**  
Not by default. You can manually generate a Paystack link outside SuoPay, but the in-app experience now assumes bank transfers. Future work may add an optional toggle per business.

**Q: How are receipts delivered?**  
When an operator marks an invoice as paid, SuoPay sends a WhatsApp receipt and reuses the existing PDF URL when available.

**Q: What happens if an invoice was marked paid by mistake?**  
You can switch the status back to `pending` or `failed` via the API. Consider logging internal notes to track reversals.

**Q: Does this affect subscription upgrades for SuoPay itself?**  
No. Paystack remains fully integrated for recurring revenue via `/subscriptions/*` routes and the `/webhooks/paystack` endpoint.

## Next Steps Summary
- Build the bank-details settings UI to let merchants self-manage payout instructions.
- Add optional proof-of-payment notes when updating invoice status.
- Explore optional automated reconciliation partners once the manual flow is stable.

**Status:** Manual bank-transfer flow is production-ready; Paystack invoice routing has been intentionally deprecated.
