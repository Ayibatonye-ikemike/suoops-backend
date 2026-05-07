# SMTP Email Configuration Guide

## SendGrid Setup (Recommended for Production)

### Why SendGrid?
- ✅ Free tier: 100 emails/day (3,000/month)
- ✅ Excellent deliverability
- ✅ Easy setup with API key
- ✅ Built-in analytics
- ✅ No credit card required for free tier

### Step-by-Step Setup

#### 1. Create SendGrid Account
1. Go to: https://signup.sendgrid.com/
2. Fill in your details
3. Verify your email address
4. Complete the account setup wizard

#### 2. Create API Key
1. Go to **Settings** → **API Keys**
2. Click **"Create API Key"**
3. **Name:** `SuoPay Production`
4. **Permissions:** Select **"Restricted Access"**
   - Check **"Mail Send"** → **Full Access**
5. Click **"Create & View"**
6. **IMPORTANT:** Copy the API key immediately (starts with `SG.`)
   - You won't be able to see it again!
   - Example: `SG.abcd1234efgh5678ijkl9012mnop3456.AbCdEfGhIjKlMnOpQrStUvWxYz1234567890AbCdEf`

#### 3. Verify Sender Identity

**Single Sender Verification (Easiest):**
1. Go to **Settings** → **Sender Authentication**
2. Click **"Verify a Single Sender"**
3. Fill in:
   - **From Name:** SuoPay
   - **From Email Address:** invoices@yourdomain.com (or your email)
   - **Reply To:** Same as above or support@yourdomain.com
   - **Company Address:** Your business address
4. Click **"Create"**
5. Check your email and click verification link

**Domain Authentication (Better for production):**
- If you own a domain, verify the entire domain
- Go to **Settings** → **Sender Authentication** → **Authenticate Your Domain**
- Follow the wizard to add DNS records

### Configuration

#### Environment Variables for Render

```bash
# SendGrid SMTP Configuration
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.your_actual_api_key_here
FROM_EMAIL=invoices@suoops.com
```

**Note:** For SendGrid, the `SMTP_USER` is literally the string `"apikey"`, and `SMTP_PASSWORD` is your API key.

#### Add to Render

```bash
render env set \
  SMTP_HOST=smtp.sendgrid.net \
  SMTP_PORT=587 \
  SMTP_USER=apikey \
  SMTP_PASSWORD=SG.your_actual_api_key_here \
  FROM_EMAIL=invoices@suoops.com \
  --app suoops-backend
```

#### Local Development (.env)

Add to your `.env` file:
```bash
# SMTP Configuration (SendGrid)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.your_actual_api_key_here
FROM_EMAIL=invoices@suoops.com
```

---

## Alternative: Gmail SMTP (For Testing Only)

### Setup Gmail App Password

1. Enable 2-Step Verification:
   - Go to: https://myaccount.google.com/security
   - Enable 2-Step Verification

2. Create App Password:
   - Go to: https://myaccount.google.com/apppasswords
   - Select **"Mail"** and **"Other (Custom name)"**
   - Name it: **"SuoPay"**
   - Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)

### Configuration

```bash
# Gmail SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=youremail@gmail.com
SMTP_PASSWORD=abcdefghijklmnop  # 16-char app password (no spaces)
FROM_EMAIL=youremail@gmail.com
```

**Gmail Limitations:**
- ⚠️ 500 emails/day limit
- ⚠️ May be flagged as spam
- ⚠️ Not recommended for production
- ✅ Good for development/testing

---

## Alternative: Other Email Providers

### Mailgun
```bash
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=postmaster@yourdomain.mailgun.org
SMTP_PASSWORD=your_mailgun_password
FROM_EMAIL=invoices@yourdomain.com
```

### Amazon SES
```bash
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your_ses_smtp_username
SMTP_PASSWORD=your_ses_smtp_password
FROM_EMAIL=invoices@yourdomain.com
```

### Outlook/Office 365
```bash
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=youremail@outlook.com
SMTP_PASSWORD=your_outlook_password
FROM_EMAIL=youremail@outlook.com
```

---

## Testing Email Functionality

### 1. Test via API

```bash
# Create invoice with customer email
curl -X POST https://api.suoops.com/invoices \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Test Customer",
    "customer_email": "test@example.com",
    "customer_phone": "+2348012345678",
    "amount": 10000,
    "lines": [{
      "description": "Test Invoice Item",
      "quantity": 1,
      "unit_price": 10000
    }]
  }'
```

### 2. Check Render Logs

```bash
# Monitor logs for email sending
Render logs --tail --app suoops-backend | grep -i "email\|smtp"
```

### 3. Expected Log Output

**Success:**
```
INFO | app.services.notification_service | Sent invoice email to test@example.com for invoice INV-XXXXXX
```

**Failure (SMTP not configured):**
```
WARNING | app.services.notification_service | SMTP not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
```

---

## Email Template

The system sends professional emails with:

```
Subject: New Invoice - INV-XXXXXX

Body:
Hello [Customer Name],

Your invoice INV-XXXXXX for ₦10,000.00 has been generated.

Invoice Details:
- Invoice ID: INV-XXXXXX
- Amount: ₦10,000.00
- Status: PENDING
- Due Date: January 1, 2025

Please find your invoice attached as a PDF.

Thank you for your business!

---
Powered by SuoPay
```

**Attachment:** Invoice PDF with logo and bank details

---

## Troubleshooting

### Issue: "SMTP not configured" warning
**Solution:** 
- Verify all 4 env vars are set: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- Check Render config: `render env ls --service suoops-backend | grep SMTP`

### Issue: "Authentication failed"
**Solution:**
- **SendGrid:** Verify API key is correct and has "Mail Send" permission
- **Gmail:** Ensure you're using App Password, not regular password
- **Gmail:** Enable 2-Step Verification first

### Issue: Emails going to spam
**Solution:**
- **SendGrid:** Verify sender identity or domain
- **Gmail:** Not recommended for production (use SendGrid)
- Add SPF and DKIM records to your domain

### Issue: "Connection refused" or timeout
**Solution:**
- Check `SMTP_PORT` is 587 (not 465 or 25)
- Verify `SMTP_HOST` is correct
- Check if Render allows SMTP connections (it does by default)

### Issue: Email sent but customer didn't receive
**Solution:**
- Check spam/junk folder
- Verify customer email address is correct
- Check SendGrid Activity Feed for delivery status
- Verify sender identity is verified in SendGrid

---

## SendGrid Dashboard

### Monitor Email Activity
1. Go to **Activity** in SendGrid dashboard
2. View all sent emails, opens, clicks, bounces
3. Filter by date, email, status

### Check Delivery Status
- **Delivered:** Email successfully delivered
- **Bounced:** Email address doesn't exist
- **Dropped:** Email not sent (unsubscribed, spam, etc.)
- **Deferred:** Temporary issue, will retry

---

## Best Practices

### Security
✅ Never commit SMTP credentials to git
✅ Use environment variables only
✅ Rotate API keys every 90 days
✅ Use restricted access (Mail Send only)

### Deliverability
✅ Verify sender identity/domain
✅ Use professional "From" email (invoices@yourdomain.com)
✅ Include unsubscribe link (for marketing emails)
✅ Monitor bounce rates

### Testing
✅ Test with real email addresses
✅ Check spam folder
✅ Verify PDF attachment opens correctly
✅ Test on mobile email clients

---

## Cost Comparison

### SendGrid
- **Free Tier:** 100 emails/day (3,000/month)
- **Essentials:** $19.95/month → 50,000 emails
- **Pro:** $89.95/month → 100,000 emails

### Mailgun
- **Free Tier:** 5,000 emails/month (3 months)
- **Pay as you go:** $0.80 per 1,000 emails

### Amazon SES
- **Free Tier:** 62,000 emails/month (if sent from EC2)
- **Pay as you go:** $0.10 per 1,000 emails

### Gmail
- **Free:** 500 emails/day
- **Not suitable for production**

---

## Next Steps

1. ✅ Create SendGrid account
2. ✅ Generate API key
3. ✅ Verify sender identity
4. ✅ Add environment variables to Render
5. ✅ Test invoice creation with email
6. ✅ Monitor SendGrid dashboard for delivery

**After setup, all invoices created with customer emails will automatically send professional email notifications with PDF attachments!** 📧

---

**Configuration Date:** October 22, 2025  
**Email Provider:** SendGrid  
**Free Tier:** 100 emails/day
