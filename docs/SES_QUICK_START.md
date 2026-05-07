# Amazon SES Quick Start Guide

**⏱️ Time Required**: 15-20 minutes  
**Region**: eu-north-1 (Europe - Stockholm)

---

## 📋 Quick Checklist

Follow these steps in order:

### ☐ Step 1: Verify Domain in SES (5 minutes)

1. Go to: https://console.aws.amazon.com/ses/ (select **eu-north-1** region)
2. Click **"Verified identities"** → **"Create identity"**
3. Select **"Domain"**, enter: `suoops.com`
4. Keep defaults, **uncheck** "Publish DNS records to Route 53"
5. Click **"Create identity"**
6. **Copy the 3 DKIM CNAME records** shown on the next page

---

### ☐ Step 2: Add DNS Records to Vercel (5 minutes)

**Via Vercel Dashboard**:
1. Go to: https://vercel.com/dashboard
2. Select project → **Settings** → **Domains** → **suoops.com**
3. Add 3 CNAME records from SES (format: `something._domainkey`)

**Via Vercel CLI** (faster):
```bash
# Replace with your actual DKIM tokens from SES
vercel dns add suoops.com <token1>._domainkey CNAME <token1>.dkim.amazonses.com
vercel dns add suoops.com <token2>._domainkey CNAME <token2>.dkim.amazonses.com
vercel dns add suoops.com <token3>._domainkey CNAME <token3>.dkim.amazonses.com
```

---

### ☐ Step 3: Wait for Verification (5-10 minutes)

1. Go back to SES Console
2. Refresh **"Verified identities"** page
3. Wait for status to change from **"Pending"** to **"Verified"** ✅

**Check DNS propagation**:
```bash
dig <token>._domainkey.suoops.com CNAME
```

---

### ☐ Step 4: Create SMTP Credentials (2 minutes)

1. In SES Console, click **"SMTP Settings"** (left sidebar)
2. Scroll to "Create SMTP credentials"
3. Click **"Create SMTP credentials"**
4. User name: `suoops-ses-smtp-user`
5. Click **"Create user"**
6. **⚠️ COPY BOTH VALUES** (you won't see password again):
   - SMTP Username: `AKIAXXXXXXXXXX`
   - SMTP Password: `XXXXXXXXXXXXXXXX`

---

### ☐ Step 5: Configure Render (2 minutes)

```bash
render env set \
  SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com \
  SES_SMTP_PORT=587 \
  SES_SMTP_USER=<your-smtp-username> \
  SES_SMTP_PASSWORD=<your-smtp-password> \
  FROM_EMAIL=noreply@suoops.com \
  -a suoops-backend
```

---

### ☐ Step 6: Test Email Sending (1 minute)

```bash
cd /Users/ayibatonyeikemike/mywork/suopay.io
.venv/bin/python test_ses_email.py
```

Enter your email when prompted to receive test email.

---

## 🎯 Expected Results

### Success Output:
```
📧 Testing Amazon SES Email Configuration...
📋 Email Configuration:
  SMTP Host: email-smtp.eu-north-1.amazonaws.com
  SMTP Port: 587
  From Email: noreply@suoops.com

📤 Sending test email to your-email@example.com...
🔌 Connecting to email-smtp.eu-north-1.amazonaws.com:587...
🔒 Starting TLS encryption...
🔑 Authenticating...
📧 Sending email...

✅ EMAIL SENT SUCCESSFULLY!
📬 Check your inbox at: your-email@example.com
```

### If Domain Not Verified:
- **Error**: `MessageRejected: Email address is not verified`
- **Solution**: Wait for DNS verification (Step 3)

### If SMTP Auth Fails:
- **Error**: `SMTPAuthenticationError: 535 Authentication failed`
- **Solution**: Double-check username/password, regenerate if needed

---

## 📊 Current Status (Sandbox Mode)

Until you request production access:

| Feature | Sandbox | Production |
|---------|---------|------------|
| Send to verified emails only | ✅ | ❌ |
| Send to any email | ❌ | ✅ |
| Daily limit | 200 emails | 50,000+ emails |
| Rate limit | 1 email/sec | 14 emails/sec |

**You can test in sandbox mode**, but for real users you need production access.

---

## ☐ Step 7: Request Production Access (Optional, takes 24h)

1. **SES Console** → **"Account dashboard"** → **"Request production access"**
2. **Fill form**:
   ```
   Use case: Transactional
   Website: https://suoops.com
   Description:
   SuoOps sends transactional emails for:
   - Invoice receipts to customers
   - Payment confirmations
   - Password reset emails
   - System notifications
   
   Expected volume: 500 emails/day
   We handle bounces and complaints properly.
   ```
3. **Submit** (approval usually takes 24 hours)

---

## 🔍 Verify Configuration

### Check Render Config:
```bash
render env get SES_SMTP_HOST --service suoops-backend
render env get SES_SMTP_USER --service suoops-backend
render env get FROM_EMAIL --service suoops-backend
```

### Check Domain Status:
```bash
# Should return CNAME records
dig _domainkey.suoops.com CNAME
```

### Test SMTP Connection:
```bash
openssl s_client -connect email-smtp.eu-north-1.amazonaws.com:587 -starttls smtp
```

---

## 💰 Pricing

| Volume | Cost/Month |
|--------|------------|
| 100 emails/day (3,000/mo) | $0.30 |
| 500 emails/day (15,000/mo) | $1.50 |
| 1,000 emails/day (30,000/mo) | $3.00 |

**Rate**: $0.10 per 1,000 emails (sent from Render)

---

## 🚨 Troubleshooting

### DNS Records Not Propagating
```bash
# Force refresh DNS
dig +trace <token>._domainkey.suoops.com
```

### SMTP Connection Timeout
- Check region: Must be `eu-north-1`
- Check firewall: Allow port 587 outbound

### Emails in Spam
- Wait for DKIM verification to complete
- Request production access
- Add SPF record (optional):
  ```
  Type: TXT
  Name: suoops.com
  Value: v=spf1 include:amazonses.com ~all
  ```

---

## 📚 Full Documentation

For detailed instructions, see: [`docs/SES_SETUP_GUIDE.md`](./SES_SETUP_GUIDE.md)

---

## ✅ Next Steps After Setup

1. Update email templates in `templates/`
2. Integrate email service in invoice creation
3. Set up bounce/complaint handling
4. Monitor email metrics in SES console

---

**Need help?** See the full guide or AWS SES documentation.
