# SuoPay Customer Invoice Flow

## Complete End-to-End User Journey

### 1️⃣ Business Creates Invoice via WhatsApp Bot

**Business sends message:**
```
Invoice Jane Smith 75000 for Logo Design due tomorrow
```

**What happens:**
- ✅ WhatsApp bot parses the message using NLP
- ✅ Invoice is created in database
- ✅ Payment link is generated via Paystack
- ✅ Invoice PDF is generated
- ✅ PDF is uploaded to S3 storage

---

### 2️⃣ Business Receives Confirmation

**Business WhatsApp receives:**
```
✅ Invoice INV-1761135842-ABC123 created!

💰 Amount: ₦75,000.00
👤 Customer: Jane Smith
📊 Status: pending

🔗 Payment link sent to customer!
```

**Business Dashboard shows:**
- Invoice appears in dashboard with "Pending" status
- Pay Now button visible
- Payment link available to copy/share

---

### 3️⃣ Customer Receives Invoice + Payment Link

**Customer WhatsApp receives:**
```
Hello Jane Smith! 👋

You have a new invoice from your business partner.

📄 Invoice: INV-1761135842-ABC123
💰 Amount: ₦75,000.00

💳 Pay now: https://checkout.paystack.com/xxxxx

Click the link above to complete your payment securely via Paystack.
```

**Customer also receives:**
- 📎 Invoice PDF attachment: `Invoice_INV-1761135842-ABC123.pdf`
- PDF caption: "Invoice INV-1761135842-ABC123 - ₦75,000.00"

---

### 4️⃣ Customer Makes Payment

**Customer clicks payment link:**
- Opens Paystack checkout page
- Enters card details or bank transfer
- Completes payment securely

**Paystack webhook fires:**
- Sends payment confirmation to SuoPay backend
- Webhook is verified with HMAC signature

---

### 5️⃣ Business Dashboard Updates

**Real-time updates:**
- ✅ Invoice status changes from "Pending" → "Paid"
- ✅ Green checkmark appears
- ✅ Payment timestamp recorded
- ✅ Pay Now button disappears
- ✅ Receipt becomes available

---

### 6️⃣ Customer Receives Receipt

**Customer WhatsApp receives:**
```
🎉 Payment Received!

Thank you for your payment!

📄 Invoice: INV-1761135842-ABC123
💰 Amount Paid: ₦75,000.00
✅ Status: PAID

Your receipt has been generated and sent to you.
```

**Customer also receives:**
- 📎 Receipt PDF attachment: `Receipt_INV-1761135842-ABC123.pdf`
- PDF caption: "Payment Receipt - ₦75,000.00"

---

## Technical Architecture

### WhatsApp Cloud API Integration
```
Business WhatsApp → Meta Cloud API → SuoPay Backend
                                   → Customer WhatsApp
```

**Endpoints:**
- `POST /v21.0/{phone_number_id}/messages` - Send text messages
- `POST /v21.0/{phone_number_id}/messages` - Send documents (PDFs)

**Authentication:**
- Bearer token: `WHATSAPP_API_KEY`
- Phone Number ID: `WHATSAPP_PHONE_NUMBER_ID`

### Payment Flow
```
Customer → Paystack Checkout → Payment Success
         → Paystack Webhook → SuoPay Backend
         → Database Update (status=paid)
         → WhatsApp Receipt to Customer
```

### Database Records
```sql
-- Invoice created
INSERT INTO invoice (
  invoice_id, issuer_id, customer_id,
  amount, status, payment_url, pdf_url
) VALUES (
  'INV-1761135842-ABC123', 1, 5,
  75000.00, 'pending', 
  'https://checkout.paystack.com/xxxxx',
  'https://s3.amazonaws.com/invoice.pdf'
);

-- Payment received
UPDATE invoice 
SET status = 'paid', updated_at = NOW()
WHERE invoice_id = 'INV-1761135842-ABC123';
```

---

## Key Features

### ✅ Automated Customer Notifications
- Invoice with payment link sent automatically
- Receipt sent automatically after payment
- No manual intervention needed

### ✅ Real-time Updates
- Business dashboard reflects payment status instantly
- Webhook ensures immediate notification
- No polling or page refresh needed

### ✅ Multi-channel Communication
- WhatsApp for instant messaging
- PDF attachments for documentation
- Web dashboard for business management

### ✅ Secure Payment Processing
- Paystack handles all payment processing
- PCI-DSS compliant
- HMAC webhook verification
- No sensitive data stored in SuoPay

### ✅ Professional Documentation
- Branded invoice PDFs
- QR codes for easy payment
- Itemized line items
- Business information included

---

## Environment Configuration

### Production Setup (Heroku)
```bash
# Backend: api.suopay.io
ENV=prod
DATABASE_URL=postgresql://...
WHATSAPP_API_KEY=EAALmWSVt...
WHATSAPP_PHONE_NUMBER_ID=817255264808254
WHATSAPP_BUSINESS_ACCOUNT_ID=713163545130337
PAYSTACK_SECRET=sk_live_...
S3_BUCKET=whatsinvoice
```

### Frontend Setup (Vercel)
```bash
# Frontend: suopay.io
NEXT_PUBLIC_API_URL=https://api.suopay.io
```

---

## User Experience Summary

### For Business Owners
1. **Send WhatsApp message** → Invoice created instantly
2. **Dashboard confirmation** → See pending invoice
3. **Automatic notifications** → Customer gets payment link
4. **Real-time updates** → Dashboard shows when paid
5. **Zero manual work** → System handles everything

### For Customers
1. **Receive WhatsApp message** → Invoice + payment link
2. **Review PDF attachment** → See full invoice details
3. **Click payment link** → Secure Paystack checkout
4. **Complete payment** → Use card or bank transfer
5. **Receive receipt** → Automatic WhatsApp confirmation with PDF

---

## Testing the Flow

### Create Test Invoice
```bash
# Via WhatsApp (send to your WhatsApp bot):
Invoice Jane Smith 75000 for Logo Design due tomorrow

# Via API:
curl -X POST https://api.suopay.io/invoices \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Jane Smith",
    "customer_phone": "+2348023456789",
    "amount": 75000,
    "lines": [{
      "description": "Logo Design",
      "quantity": 1,
      "unit_price": 75000
    }]
  }'
```

### Test Payment Webhook
```bash
# Paystack will send to:
POST https://api.suopay.io/webhooks/paystack

# With payload:
{
  "event": "charge.success",
  "data": {
    "reference": "INV-1761135842-ABC123",
    "status": "success",
    "amount": 7500000,
    "currency": "NGN"
  }
}
```

---

## Success Metrics

### Business KPIs
- ⚡ **Invoice creation time:** < 5 seconds
- 📱 **Customer notification:** < 10 seconds
- 💳 **Payment processing:** Real-time webhook
- 📧 **Receipt delivery:** < 5 seconds after payment

### Technical Performance
- 🟢 **API uptime:** 99.9% (Heroku)
- 🟢 **Database:** PostgreSQL with connection pooling
- 🟢 **Storage:** S3 with presigned URLs
- 🟢 **Queue:** Redis + Celery for background tasks

---

## What Makes This Special

### Traditional Flow (Manual)
```
Business creates invoice → Email to customer → Customer replies
→ Business sends payment details → Customer transfers money
→ Business confirms payment → Business sends receipt
Total time: 1-2 days, multiple back-and-forth
```

### SuoPay Flow (Automated)
```
Business sends WhatsApp → Customer gets invoice + bank details
→ Customer transfers directly to business → Operator marks as paid → Receipt auto-sent
Total time: minutes instead of days, minimal back-and-forth
```

**Time saved:** ~95%  
**Messages saved:** 6-10 per transaction  
**Error reduction:** Manual entry errors eliminated  
**Customer experience:** Professional and instant

---

## Next Steps

### For Business Owners
1. Register at https://suopay.io/register
2. Connect your WhatsApp business number
3. Add your business bank details in settings
4. Start sending invoices via WhatsApp!

### For Developers
1. Review API documentation: `/docs/api_spec.md`
2. Check webhook setup: `/docs/webhooks.md`
3. Test in sandbox mode first
4. Deploy to production

---

**Built with:** FastAPI, Next.js, PostgreSQL, Redis, Celery, WhatsApp Cloud API (Paystack powers SuoPay subscription billing)
**Deployed on:** Heroku (Backend) + Vercel (Frontend)  
**Domain:** https://suopay.io + https://api.suopay.io
