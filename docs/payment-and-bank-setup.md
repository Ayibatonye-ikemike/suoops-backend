# Payment & Bank Account Setup Guide 💳

**Last Updated:** October 22, 2025  
**For:** SuoPay Business Users

---

## Overview

This guide covers two important features:
1. **How Paystack sends money to your business bank account**
2. **How to manually mark invoices as paid** (for direct bank transfers)

---

## Part 1: Paystack Bank Account Setup 🏦

### How It Works

When a customer pays via the payment link on your invoice:
1. Customer clicks payment link (e.g., `https://paystack.com/pay/inv-xxx`)
2. Customer pays via card/bank transfer on Paystack
3. **Paystack deducts their fee** (1.5% + ₦100 for local cards)
4. **Paystack automatically settles the rest to YOUR business bank account**
5. Your invoice is marked as "paid" automatically
6. Customer receives payment receipt via WhatsApp

**Important:** You DON'T pay Paystack fees - they're deducted from the payment amount before settling to you.

---

### Setting Up Your Business Bank Account

#### Step 1: Complete Paystack Business Registration

1. **Go to Paystack Dashboard**
   - Visit: https://dashboard.paystack.com/

2. **Complete Business Verification** (Required for settlements)
   - Navigate to: **Settings → Business Profile**
   - Upload required documents:
     - ✅ Business Registration Certificate (CAC)
     - ✅ Valid Government ID
     - ✅ Proof of Address
     - ✅ Bank Verification Number (BVN) - Director

3. **Business Verification Status**
   - **Before verification:** Can accept payments, but NO settlements
   - **After verification:** Automatic settlements to your bank account
   - **Verification time:** 1-3 business days

#### Step 2: Add Your Settlement Bank Account

1. **Go to Settlement Settings**
   - Dashboard → **Settings → Settlement**

2. **Add Bank Account**
   - Click **"Add Bank Account"**
   - Enter details:
     - Bank Name (e.g., GTBank, Access Bank, First Bank)
     - Account Number (10 digits)
     - Account Name (must match business registration)

3. **Verify Account**
   - Paystack will make a test deposit (₦10)
   - Confirm the amount in your dashboard
   - Account becomes active for settlements

#### Step 3: Configure Settlement Schedule

Choose how often Paystack sends money to your account:

**Option 1: Automatic Daily Settlement** (Recommended)
- **Schedule:** Every business day at 3 PM
- **Minimum:** ₦1,000 balance
- **Best for:** Businesses with regular transactions

**Option 2: Automatic Weekly Settlement**
- **Schedule:** Every Friday at 3 PM
- **Minimum:** ₦5,000 balance
- **Best for:** Businesses with fewer transactions

**Option 3: Manual Settlement**
- **Schedule:** Request manually in dashboard
- **Minimum:** ₦10,000 balance
- **Best for:** Businesses that want control

**To Configure:**
1. Dashboard → Settings → Settlement
2. Choose **Settlement Schedule**
3. Save changes

---

### Understanding Paystack Fees

#### Fee Structure (Local Cards - Nigeria):
- **Rate:** 1.5% + ₦100 capped at ₦2,000
- **Examples:**
  - ₦10,000 payment → Fee: ₦250 → You receive: ₦9,750
  - ₦50,000 payment → Fee: ₦850 → You receive: ₦49,150
  - ₦200,000 payment → Fee: ₦2,000 (capped) → You receive: ₦198,000

#### Fee Structure (Bank Transfers):
- **Rate:** ₦50 flat fee
- **Examples:**
  - ₦10,000 payment → Fee: ₦50 → You receive: ₦9,950
  - ₦50,000 payment → Fee: ₦50 → You receive: ₦49,950
  - ₦200,000 payment → Fee: ₦50 → You receive: ₦199,950

**Tip:** Encourage customers to use bank transfer for larger amounts to save on fees!

---

### How Settlement Works - Example Flow

**Scenario:** Customer pays ₦50,000 invoice via Paystack

```
Monday, 10:00 AM
├─ Customer clicks payment link
├─ Customer pays ₦50,000 via GTBank Transfer
└─ Payment successful

Monday, 10:01 AM (Instant)
├─ Paystack deducts ₦50 fee
├─ Your Paystack balance: +₦49,950
├─ Invoice marked as PAID in SuoPay
└─ Customer receives WhatsApp receipt

Tuesday, 3:00 PM (Next business day)
├─ Paystack automatic settlement runs
├─ ₦49,950 transferred to your bank account
├─ Bank alert: "Credit Alert - ₦49,950"
└─ Settlement email from Paystack
```

**Timeline:**
- Payment to Paid status: **Instant** (< 5 seconds)
- Paystack balance to Bank account: **T+1** (next business day at 3 PM)

---

### Checking Your Settlements

#### In Paystack Dashboard:
1. Go to: **Transactions → Settlements**
2. View:
   - Pending settlements (money in Paystack balance)
   - Completed settlements (money sent to bank)
   - Settlement history with dates

#### In Your Bank Account:
- Settlement reference format: `PAYSTACK-STLMT-XXXXXXXX`
- Email notification from Paystack with breakdown
- Matches your Paystack settlement report

---

### Common Issues & Solutions

#### ❌ Issue: "Settlements are pending"
**Reason:** Business not verified  
**Solution:**
1. Complete business verification (Step 1 above)
2. Upload CAC, ID, BVN documents
3. Wait 1-3 business days for approval

#### ❌ Issue: "Wrong bank account receives money"
**Reason:** Multiple bank accounts configured  
**Solution:**
1. Dashboard → Settings → Settlement
2. Remove old bank accounts
3. Set correct account as primary

#### ❌ Issue: "Settlement delayed beyond T+1"
**Reason:** Bank holidays, or balance below minimum  
**Solution:**
- Check Paystack balance (need ₦1,000 minimum)
- Verify it's not a weekend/public holiday
- Contact Paystack support if > 2 business days

#### ❌ Issue: "Received less than expected"
**Reason:** Paystack fees deducted  
**Solution:**
- Review transaction details in dashboard
- Fee breakdown shown per transaction
- This is normal - fees are always deducted

---

## Part 2: Manual Payment Confirmation 💼

### Use Case: Customer Pays Directly to Your Bank

Sometimes customers prefer to:
- Transfer directly to your business bank account
- Pay via cash
- Use alternative payment methods

**Problem:** Invoice stays "pending" because Paystack webhook never fires

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
curl -X PATCH https://api.suopay.io/invoices/{invoice_id} \
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
Webhook URL: https://api.suopay.io/webhooks/paystack
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
- **Email:** support@suopay.io
- **Dashboard:** https://suopay.io/help

---

**Last Updated:** October 22, 2025  
**Version:** 1.0  
**For:** SuoPay Business Users

