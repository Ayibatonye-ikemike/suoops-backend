# Email Automation for SuoOps Invoices

## Overview
Automatic email delivery for invoices created via Dashboard or WhatsApp with Brevo SMTP.

## 📧 Email Configuration

**Email Provider:** Brevo (Sendinblue)
- **Free Tier:** 300 emails/day
- **SMTP Host:** smtp-relay.brevo.com
- **SMTP Port:** 587 (TLS)
- **From Email:** info@suoops.com (verified sender)

**Heroku Config (v86):**
```bash
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=9a485d001@smtp-brevo.com
SMTP_PASSWORD=xsmtpsib-***
FROM_EMAIL=info@suoops.com
EMAIL_PROVIDER=gmail  # Uses SMTP_* variables
```

## ✅ How It Works

### 1. Dashboard Invoices
When creating invoices via API/Dashboard with `customer_email`:

```json
POST /invoices
{
  "customer_name": "Jane Smith",
  "customer_email": "jane@example.com",
  "amount": 50000,
  "lines": [...]
}
```

**Result:** 
- ✅ Invoice created in database
- ✅ Email sent to `jane@example.com` with PDF attachment
- ✅ Success logged

### 2. WhatsApp Invoices WITH Email

**User sends message:**
```
Invoice Jane jane@example.com 50000 for logo design
```

**System processes:**
1. NLP extracts: customer_name="Jane", customer_email="jane@example.com", amount=50000
2. Creates invoice in database
3. **Sends email** to jane@example.com with PDF
4. Sends WhatsApp message to customer (if phone provided)
5. Notifies business on WhatsApp: "✉️ Invoice email sent to customer!"

### 3. WhatsApp Invoices WITHOUT Email

**User sends message:**
```
Invoice John +2348087654321 75000 for consulting
```

**System processes:**
1. NLP extracts: customer_name="John", customer_phone="+2348087654321", amount=75000
2. Creates invoice in database
3. **No email sent** (customer_email is None)
4. Sends WhatsApp message to customer
5. Notifies business on WhatsApp: "📧 WhatsApp invoice sent to customer!"

## 📝 Email Format Examples

### Text Messages (Various formats)
```
✅ Invoice Jane 50k email jane@example.com
✅ Invoice john@company.co.uk John Smith 75000 for consulting
✅ Invoice Sarah sarah.doe@business.ng 30000 +2348087654321
✅ Invoice Peter info@suoops.com 45000 for marketing
```

### Voice Notes (Spoken)
```
🎤 "Invoice Jane, jane at example dot com, fifty thousand naira for logo design"
🎤 "Invoice John, email john at company dot com, seventy five thousand"
```

**Note:** Speech-to-text may transcribe emails as "john at company dot com" which the system will handle gracefully (won't extract invalid emails).

## 📬 Email Contents

**Subject:** New Invoice - INV-XXX-XXX

**Body:**
```
Hello [Customer Name],

Your invoice INV-XXX-XXX for ₦50,000.00 has been generated.

Invoice Details:
- Invoice ID: INV-XXX-XXX
- Amount: ₦50,000.00
- Status: PENDING
- Due Date: [Date if provided]

Please find your invoice attached as a PDF.

Thank you for your business!

---
Powered by SuoOps
```

**Attachment:** Invoice_INV-XXX-XXX.pdf

## 🔧 Technical Implementation

### NLP Service (`app/bot/nlp_service.py`)
- **Email Pattern:** `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
- **Method:** `_extract_email(text)` returns lowercase email or None
- **Integration:** Added to `_extract_invoice()` entities dict

### Invoice Intent Processor (`app/bot/invoice_intent_processor.py`)
- **Method:** `_send_invoice_email(invoice, recipient_email)`
- **Uses:** `NotificationService.send_invoice_email()`
- **Error Handling:** Logs failures, doesn't block invoice creation
- **Business Notification:** Shows email status in WhatsApp message

### Notification Service (`app/services/notification_service.py`)
- **Method:** `send_invoice_email(invoice, recipient_email, pdf_url, subject)`
- **SMTP:** Uses `_get_smtp_config()` based on EMAIL_PROVIDER
- **PDF Attachment:** Downloads from S3 URL and attaches to email
- **TLS Security:** Uses STARTTLS on port 587

## 🧪 Testing

### Email Extraction Test
```bash
python3 test_email_extraction.py
```

**Results:** 5/5 tests pass
- ✅ Email at end of message
- ✅ Email in middle of message
- ✅ Email with phone number
- ✅ No email (gracefully handles)
- ✅ Business email formats

### Manual Testing

**1. Test via API:**
```bash
curl -X POST https://api.suoops.com/invoices \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Test User",
    "customer_email": "test@example.com",
    "amount": 10000,
    "lines": [{"description": "Test", "quantity": 1, "unit_price": 10000}]
  }'
```

**2. Test via WhatsApp:**
Send to SuoOps bot: `Invoice Test test@example.com 10000 for testing`

**3. Check Logs:**
```bash
heroku logs --tail | grep email
```

## 📊 Email Delivery Monitoring

### Brevo Dashboard
- Login: https://app.brevo.com
- Monitor: Campaigns → Transactional → Email activity
- Check: Delivery rate, opens, bounces, spam reports

### Application Logs
```bash
# View email sending logs
heroku logs --tail | grep "Invoice email"

# Success example:
INFO: Invoice email sent to jane@example.com for invoice INV-123-456

# Failure example:
WARNING: Failed to send invoice email to invalid@email
```

## ⚠️ Troubleshooting

### Email Not Received

**1. Check Brevo Sender Verification**
- Login to Brevo dashboard
- Go to "Senders, Domains & Dedicated IPs"
- Verify `info@suoops.com` has green "Verified" badge
- If not verified, add and verify the sender

**2. Check Spam/Junk Folder**
- First emails from new senders often go to spam
- Mark as "Not Spam" to improve future deliverability

**3. Check Email Format**
- Email must be valid format: `user@domain.com`
- Check logs for extraction: `heroku logs --tail | grep email`

**4. Check Brevo Quota**
- Free tier: 300 emails/day
- Monitor usage in Brevo dashboard
- Upgrade if needed

### Email Extraction Not Working

**1. Test Locally**
```bash
python3 test_email_extraction.py
```

**2. Check Message Format**
- Email must be complete: `jane@example.com`
- Avoid typos: `jane@examplecom` (missing dot)
- Include TLD: `.com`, `.ng`, `.co.uk`, etc.

**3. View Extracted Entities**
```bash
heroku logs --tail | grep "entities"
```

### SMTP Connection Issues

**1. Verify Credentials**
```bash
heroku config:get SMTP_USER
heroku config:get SMTP_HOST
```

**2. Test SMTP Connection**
```bash
heroku run python test_email.py
```

**3. Check Brevo Status**
- https://status.brevo.com
- Verify no service disruptions

## 🔒 Security Best Practices

1. **Never expose SMTP credentials** in code or logs
2. **Use environment variables** for all sensitive config
3. **Validate email addresses** before sending (regex pattern)
4. **Rate limit** email sending to prevent abuse
5. **Monitor Brevo dashboard** for suspicious activity
6. **Use verified sender** (info@suoops.com) to avoid spam

## 📈 Usage Statistics

### Current Limits (Brevo Free Tier)
- **Daily Limit:** 300 emails/day
- **Monthly Limit:** ~9,000 emails/month
- **Cost:** ₦0 (free tier)

### Typical Usage
- **1 invoice = 1 email** (to customer)
- **10 customers/day = 10 emails/day**
- **300 invoices/day max** (within free tier)

### Upgrade Options (if needed)
- **Lite Plan:** $25/month = 10,000 emails/month
- **Standard Plan:** $65/month = 20,000 emails/month
- **Premium Plan:** $65/month + $1 per 1,000 additional emails

## 🎯 User Experience

### Business Owner Perspective
1. Creates invoice via WhatsApp or Dashboard
2. Includes customer email in message
3. Receives confirmation: "✉️ Invoice email sent to customer!"
4. Customer gets professional email with PDF
5. No manual email sending needed

### Customer Perspective
1. Receives WhatsApp message (if phone provided)
2. **Also receives email** with PDF attachment
3. Can view invoice on any device
4. Can save/print PDF for records
5. Professional email experience

## ✅ Production Checklist

- [x] Brevo account created
- [x] SMTP credentials configured (Heroku v86)
- [x] `info@suoops.com` verified in Brevo
- [x] Email extraction implemented (NLP)
- [x] Email sending integrated (Intent Processor)
- [x] Tests passing (5/5 email extraction)
- [x] Deployed to production (v86)
- [ ] Domain authentication (DKIM/DMARC) - Optional for better deliverability
- [ ] Custom sender `noreply@suoops.com` verification - Optional

## 📚 Additional Resources

- **Brevo Docs:** https://developers.brevo.com/
- **Email Setup Guide:** `docs/email-setup.md`
- **S3 Setup Guide:** `docs/s3-setup.md` (for PDF storage)
- **WhatsApp Guide:** `docs/deployment-guide.md`

## 🚀 Next Steps

1. **Monitor email deliverability** in Brevo dashboard
2. **Collect user feedback** on email feature
3. **Consider domain authentication** (DKIM/DMARC) for better deliverability
4. **Add email tracking** (opens, clicks) using Brevo events
5. **Create email templates** for different invoice types
