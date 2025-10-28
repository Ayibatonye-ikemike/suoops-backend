# Payment & Bank Account Setup Guide 💳

**Last Updated:** October 24, 2025  
**Audience:** SuoPay merchants configuring manual bank-transfer invoices

---

## Overview

SuoPay invoices now default to **direct bank transfers**. Every invoice and WhatsApp notification highlights your bank instructions so customers can pay you without leaving the SuoPay experience. This guide covers:
1. Capturing or updating the bank account details that appear on invoices
2. Best practices for sharing those instructions with customers
3. How to confirm payments manually inside SuoPay once funds arrive
4. Where Paystack is still used (hint: only for paying SuoPay subscription fees)

---

## Part 1: Configure the Bank Details Shown on Invoices 🏦

### What Merchants Need on File
- `business_name` – how you want to appear on invoices and receipts
- `bank_name` – e.g. Access Bank, GTBank, Zenith
- `account_name` – account holder name the bank expects
- `account_number` – 10-digit NUBAN for NGN accounts

These fields live on your SuoPay user profile. Without them, invoices are still generated, but the payment instruction block will be blank.

### Update via API (until the dashboard UI ships)

Use either `PATCH` or `POST` on `PATCH /me/bank-details` with an authenticated request. Example using curl:

```bash
curl -X PATCH "https://api.suoops.com/me/bank-details" \
   -H "Authorization: Bearer <ACCESS_TOKEN>" \
   -H "Content-Type: application/json" \
   -d '{
            "business_name": "Lagos Design Studio",
            "bank_name": "GTBank",
            "account_name": "Lagos Design Studio LTD",
            "account_number": "0123456789"
         }'
```

**Validation reminders:**
- Account numbers must be exactly 10 digits (NUBAN format)
- You can update one field at a time; only send the keys you want to change
- Deleting details (`DELETE /me/bank-details`) removes them from future invoices until you set them again

### Viewing the Stored Details

Call `GET /me/bank-details` to confirm what the system will render:

```bash
curl -H "Authorization: Bearer <ACCESS_TOKEN>" \
   https://api.suoops.com/me/bank-details
```

Response shape:

```json
{
   "business_name": "Lagos Design Studio",
   "bank_name": "GTBank",
   "account_name": "Lagos Design Studio LTD",
   "account_number": "0123456789",
   "is_configured": true
}
```

Once `is_configured` is `true`, invoice PDFs and WhatsApp messages display the payment block automatically.

### How the Details Appear to Customers

PDF invoices include a prominent “Payment Instructions” card as soon as any bank field is present. WhatsApp notifications also mirror the bank name + account number so customers know exactly where to transfer funds.

Tip: upload your business logo (`POST /me/logo`) so the invoice PDF looks polished when you share it.

---

## Part 2: Share Payment Instructions Confidently 📄

1. **Confirm the bank details before issuing invoices.** Run `GET /me/bank-details` or send yourself a sample invoice to verify formatting.
2. **Communicate timelines.** Add a note to invoices (or the WhatsApp follow-up) that payments must be confirmed before services are delivered.
3. **Encourage a payment reference.** Ask payers to include the invoice ID in the transfer narration so reconciliation is easier (`INV-1234` works great).
4. **Keep proof-of-payment handy.** Until the dashboard adds attachments, store screenshots or alerts in your own drive for audit trails.

---

## Part 3: Manually Confirm Customer Payments ✅

When the customer shares proof or your bank alert lands, update the invoice status yourself.

### Step-by-step

1. **Verify the transfer.** Check your bank statement, mobile alert, or POS dashboard. Confirm the amount matches the invoice total.
2. **Mark the invoice as paid.**

```bash
curl -X PATCH "https://api.suoops.com/invoices/INV-1234" \
   -H "Authorization: Bearer <ACCESS_TOKEN>" \
   -H "Content-Type: application/json" \
   -d '{"status": "paid"}'
```

3. **Notify the customer.** SuoPay automatically sends the WhatsApp receipt and attaches the PDF again if available.
4. **Handle mistakes.** If funds bounce or you toggled the wrong invoice, send `status": "pending"` or `"failed"` to reverse the update.

### Optional: Capture Internal Notes

Many teams store a lightweight ledger outside SuoPay with fields such as:
- Payment reference (transfer narration or bank sequence number)
- Verifier name and timestamp
- Extra comments (e.g. “partial payment ₦50k, balance due Friday”)

Future product work may bring these note fields directly into the dashboard.

---

## Part 4: Where Paystack Fits Now (Subscriptions Only) 🔄

SuoPay still uses Paystack **only** for charging your business when you upgrade plans or buy add-ons. This flow lives under `/subscriptions/*` and the Paystack webhook listens exclusively for `charge.success` events tied to SuoPay billing.

Nothing about Paystack is required for your customer invoices:
- No payment links are generated in the invoice lifecycle
- No invoice webhooks from Paystack are processed
- Settlements go directly from your customer to your bank

If you personally prefer Paystack payment links for certain clients, you can create them outside SuoPay. Just remember to mark the invoice as `paid` manually once you confirm the funds.

---

## Part 5: Troubleshooting & FAQs 🔍

### Customers say they did a transfer, but you can’t find it
- Double-check your bank app for delayed alerts
- Ask for the transfer reference and match against your statement
- If still missing, set the invoice to `pending` and follow up; do not mark `paid` until cash is confirmed

### Bank details missing from the PDF
- Run `GET /me/bank-details` and ensure `is_configured` is `true`
- Make sure each field was sent in the update request (empty strings are ignored)
- Recreate the invoice after updating details—the PDF captures the snapshot at generation time

### Switching bank accounts
- Send a `PATCH /me/bank-details` request with the new bank name + number
- Existing invoices keep the old instructions (they’re embedded in the PDF); issue a new invoice or notify customers of the change

### Need to erase details temporarily
- Call `DELETE /me/bank-details`
- Remember to reapply the fields before creating fresh invoices; otherwise the payment block is hidden

### Do merchants owe Paystack fees for invoices now?
- No. Because SuoPay no longer routes invoice payments through Paystack, there are no gateway deductions. Customers pay you directly and your bank statement is the source of truth.

---

## Quick Checklist Before Going Live ✅
- [ ] Bank details configured and verified via API
- [ ] Sample invoice generated to confirm formatting
- [ ] Internal process documented for verifying transfers (who checks alerts, how often)
- [ ] Team trained on using `PATCH /invoices/{id}` to update status
- [ ] Optional: Logo uploaded for branded PDFs

With these pieces in place, you can confidently issue invoices that guide customers to pay your business account, while keeping SuoPay focused on automation, documentation, and customer communications.

**Solution:** Manually mark invoice as "paid" from your dashboard

---

### How to Mark Invoice as Paid Manually

#### Via Dashboard (Recommended):

1. **Navigate to Invoices**
   - Dashboard → Invoices
   - Find the invoice paid by customer

2. **Click Invoice to View Details**
   - Shows: Invoice ID, Amount, Status, Customer

3. **Change Status to "Paid"**
   - Click **"Mark as Paid"** button
   - OR: Status dropdown → Select "Paid" → Click "Update"

4. **Receipt Sent Automatically** ✅
   - System sends WhatsApp receipt to customer
   - Same receipt as Paystack automatic payment
   - Includes: Invoice ID, Amount, "PAID" status, PDF

#### Via API (For Custom Integrations):

```bash
curl -X PATCH https://api.suoops.com/invoices/{invoice_id} \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"status": "paid"}'
```

**Response:**
```json
{
  "invoice_id": "INV-20251022-ABC123",
  "amount": 50000.00,
  "status": "paid",
  "customer": {
    "name": "Jane Doe",
    "phone": "+2348012345678"
  }
}
```

**What Happens:**
1. ✅ Invoice status updated to "paid"
2. ✅ WhatsApp receipt sent to customer automatically
3. ✅ PDF receipt sent to customer
4. ✅ Invoice marked as paid in your dashboard
5. ✅ Metrics updated (invoice_paid counter)

---

### Receipt Contents

When you manually mark as paid, customer receives:

**WhatsApp Message:**
```
🎉 Payment Received!

Thank you for your payment!

📄 Invoice: INV-20251022-ABC123
💰 Amount Paid: ₦50,000.00
✅ Status: PAID

Your receipt has been generated and sent to you.
```

**PDF Attachment:**
- Professional receipt document
- Invoice details and line items
- "PAID" stamp
- Your business details

---

### When to Use Manual vs Automatic Payment

#### Use **Paystack Automatic** (Recommended) When:
✅ Customer has debit/credit card  
✅ Customer prefers online payment  
✅ You want instant confirmation  
✅ You want automated receipt sending  
✅ Customer is not tech-savvy (Paystack UI is simple)

**Advantages:**
- No manual work
- Instant payment confirmation
- Automatic receipt sending
- Better tracking and reports
- Paystack handles disputes

#### Use **Manual Payment Confirmation** When:
✅ Customer insists on direct bank transfer  
✅ Customer pays via cash  
✅ Payment through POS terminal  
✅ Customer uses alternative payment (mobile money, etc.)  
✅ Large payment (customer wants to avoid card fees)

**Disadvantages:**
- You must manually verify payment received
- Risk of fraud (unverified payments)
- Extra manual work
- No Paystack dispute protection

---

### Best Practices for Manual Payments

#### ✅ DO:
1. **Verify payment in your bank account first** before marking as paid
2. **Screenshot bank alert** as proof of payment
3. **Ask customer for payment reference** (bank transfer reference)
4. **Keep records** of all manual payments
5. **Inform customer** that receipt will be sent via WhatsApp

#### ❌ DON'T:
1. **Don't mark as paid** before receiving money
2. **Don't skip verification** - check your actual bank account
3. **Don't forget to tell customer** to wait for receipt
4. **Don't use manual payment** if Paystack works (more secure)

---

### Example Workflow: Direct Bank Transfer

**Step-by-Step:**

1. **Customer Requests Direct Transfer**
   - Customer: "I want to pay directly to your account"
   - You: "Sure! Our account details are..."

2. **Share Your Bank Details**
   ```
   Bank: GTBank
   Account Number: 0123456789
   Account Name: My Business Ltd
   Amount: ₦50,000
   Reference: INV-20251022-ABC123 (important!)
   ```

3. **Customer Makes Transfer**
   - Customer transfers ₦50,000 to your account
   - Customer sends you bank alert screenshot
   - You verify in your bank app

4. **You Mark Invoice as Paid**
   - Dashboard → Find invoice INV-20251022-ABC123
   - Click "Mark as Paid"
   - System sends receipt to customer automatically

5. **Customer Receives Receipt**
   - WhatsApp message: "🎉 Payment Received!"
   - PDF receipt attached
   - Customer is happy! ✅

---

## Part 3: Paystack Integration in SuoPay 🔗

### How SuoPay Uses Paystack

#### 1. Payment Link Generation
When you create an invoice via WhatsApp or Dashboard:
```python
# SuoPay creates Paystack payment link
payment_link = f"https://paystack.com/pay/{invoice_id}"
# Sent to customer via WhatsApp
```

#### 2. Webhook Configuration
Paystack sends payment confirmations to SuoPay:
```
Webhook URL: https://api.suoops.com/webhooks/paystack
Events: charge.success, transfer.success
```

#### 3. Automatic Status Update
When customer pays via Paystack:
1. Paystack sends webhook to SuoPay
2. SuoPay marks invoice as "paid"
3. SuoPay sends receipt to customer
4. All automatic - no manual work!

---

### Paystack Dashboard Access

#### Important URLs:
- **Dashboard:** https://dashboard.paystack.com/
- **Transactions:** https://dashboard.paystack.com/transactions
- **Settlements:** https://dashboard.paystack.com/settlements
- **API Keys:** https://dashboard.paystack.com/settings/developer

#### What You Can See:
- All payments received
- Settlement history
- Transaction fees breakdown
- Customer payment details
- Refund/dispute management

---

## Part 4: Pricing Comparison ⚖️

### Cost of Payment Processing

#### Option 1: Paystack (Automatic) - Card Payment
```
Customer pays: ₦50,000
Paystack fee: ₦850 (1.5% + ₦100)
You receive: ₦49,150
Your cost: ₦0 (fee deducted from payment)
Time to bank: T+1 (next business day)
```

#### Option 2: Paystack (Automatic) - Bank Transfer
```
Customer pays: ₦50,000
Paystack fee: ₦50 (flat)
You receive: ₦49,950
Your cost: ₦0 (fee deducted from payment)
Time to bank: T+1 (next business day)
```

#### Option 3: Direct Bank Transfer (Manual)
```
Customer pays: ₦50,000
Bank charges: ₦0-50 (customer pays, not you)
You receive: ₦50,000
Your cost: ₦0
Time to bank: Instant
Manual work: Yes (verify + mark as paid)
```

### Which Option is Best?

#### For Small Amounts (< ₦10,000):
- ✅ **Paystack Bank Transfer** (₦50 flat fee)
- ✅ **Direct Transfer** (if customer insists)

#### For Medium Amounts (₦10,000 - ₦100,000):
- ✅ **Paystack Bank Transfer** (₦50 flat fee)
- ⚠️ Paystack Card (1.5% can add up)

#### For Large Amounts (> ₦100,000):
- ✅ **Direct Bank Transfer** (₦0 fee, save on 1.5%)
- ✅ **Paystack Bank Transfer** (₦50 flat fee)
- ❌ Paystack Card (₦2,000 fee capped, but still high)

---

## Part 5: Troubleshooting 🔧

### Issue: Customer Can't Open Payment Link

**Symptoms:**
- Link doesn't work
- Shows "Page not found"
- Payment page doesn't load

**Solutions:**
1. Check Paystack account is active
2. Verify invoice has `payment_url` set
3. Check Paystack API key is configured in SuoPay
4. Test payment link in incognito browser
5. Ask customer to try different browser/device

---

### Issue: Invoice Not Marked as Paid After Customer Paid

**Symptoms:**
- Customer shows proof of payment
- Invoice still shows "pending" in dashboard
- Customer didn't receive receipt

**Check:**
1. **Was payment via Paystack link?**
   - If YES: Check Paystack webhook configuration
   - If NO: Manually mark as paid (customer paid directly to your bank)

2. **Verify in Paystack Dashboard:**
   - Go to Transactions
   - Search for invoice ID or amount
   - Check payment status in Paystack

3. **Check Webhook Logs:**
   - Heroku logs: `heroku logs --tail | grep webhook`
   - Look for webhook received and processed

**Solution:**
- If payment found in Paystack but not in SuoPay: Check webhook URL configuration
- If payment NOT in Paystack: Customer paid directly → Mark manually
- If webhook failed: Check logs, may need to manually mark as paid

---

### Issue: Customer Received Multiple Receipts

**Symptoms:**
- Customer complains about spam
- Multiple WhatsApp messages sent

**Causes:**
1. Marked as paid manually + Paystack webhook fired
2. Multiple webhook deliveries from Paystack
3. Duplicate payment from customer

**Prevention:**
- Check invoice status before manually marking as paid
- System already prevents duplicate webhook processing
- Educate customer to pay only once

---

## Part 6: Advanced Configuration ⚙️

### Custom Settlement Preferences

#### Split Settlements (Coming Soon)
Send part of payment to multiple accounts:
```
Example: Agency invoicing for client
- 80% to client account
- 20% to agency account (commission)
```

#### Multi-Currency (Coming Soon)
Accept payments in:
- USD (for international clients)
- GBP, EUR (other currencies)
- Auto-convert to NGN at settlement

---

### Security Best Practices

#### Protect Your Paystack Account:
1. ✅ Enable 2FA (Two-Factor Authentication)
2. ✅ Use strong password (12+ characters)
3. ✅ Never share API keys publicly
4. ✅ Rotate API keys every 90 days
5. ✅ Restrict API key permissions (production vs test)

#### In SuoPay Settings:
1. ✅ Only admins can mark invoices as paid
2. ✅ Log all manual status changes
3. ✅ Require verification before marking paid
4. ✅ Review manual payments weekly

---

## Summary Checklist ✅

### Initial Setup (One-Time):
- [ ] Create Paystack account
- [ ] Complete business verification (CAC, ID, BVN)
- [ ] Add business bank account
- [ ] Configure settlement schedule (daily recommended)
- [ ] Set up webhook URL in Paystack dashboard
- [ ] Test with small payment (₦100)

### For Each Invoice (Automatic via Paystack):
- [ ] Create invoice in SuoPay
- [ ] Payment link automatically generated
- [ ] Customer receives WhatsApp message with link
- [ ] Customer pays via Paystack
- [ ] Invoice automatically marked as paid
- [ ] Receipt automatically sent to customer
- [ ] Money settles to bank account next business day

### For Direct Bank Transfers (Manual):
- [ ] Customer requests to pay directly
- [ ] Share your bank account details
- [ ] Customer transfers money
- [ ] Verify payment received in your bank account
- [ ] Mark invoice as paid in SuoPay dashboard
- [ ] System automatically sends receipt to customer

---

## Need Help?

### Paystack Support:
- **Email:** support@paystack.com
- **Phone:** +234 1 888 3888
- **Live Chat:** https://dashboard.paystack.com/

### SuoPay Support:
- **WhatsApp:** +234 XXX XXX XXXX (your support number)
- **Email:** support@suoops.com
- **Dashboard:** https://suoops.com/help

---

**Last Updated:** October 22, 2025  
**Version:** 1.0  
**For:** SuoPay Business Users

