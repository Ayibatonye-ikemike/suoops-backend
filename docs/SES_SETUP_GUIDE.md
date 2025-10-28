# Amazon SES Setup for SuoOps Email Notifications

**Date**: October 28, 2025  
**Domain**: suoops.com  
**Region**: eu-north-1 (Europe - Stockholm)  
**Purpose**: Transactional emails (invoice receipts, notifications, password resets)

---

## Prerequisites ✅

- [x] Domain registered: suoops.com
- [x] DNS managed by: Vercel (ns1.vercel-dns.com, ns2.vercel-dns.com)
- [x] AWS Account with SES access in eu-north-1
- [ ] DNS access to add verification records

---

## Step 1: Verify Your Domain in Amazon SES

### 1.1 Start Domain Verification

1. **Go to Amazon SES Console**: https://console.aws.amazon.com/ses/
2. **Select Region**: Europe (Stockholm) `eu-north-1` (top-right corner)
3. **Click "Verified identities"** (left sidebar)
4. **Click "Create identity"**
5. **Select**: Domain
6. **Domain name**: `suoops.com`
7. **Use a default DKIM signing key**: Selected (recommended)
8. **DKIM signing key length**: RSA_2048_BIT
9. **Publish DNS records to Route 53**: UNCHECK (we use Vercel DNS)
10. **Click "Create identity"**

### 1.2 Get DNS Records

After creating, you'll see a page with **3 DNS records to add**:

#### Record 1: DKIM Record 1
```
Type: CNAME
Name: abc123def._domainkey.suoops.com
Value: abc123def.dkim.amazonses.com
```

#### Record 2: DKIM Record 2
```
Type: CNAME
Name: xyz789ghi._domainkey.suoops.com
Value: xyz789ghi.dkim.amazonses.com
```

#### Record 3: DKIM Record 3
```
Type: CNAME
Name: jkl456mno._domainkey.suoops.com
Value: jkl456mno.dkim.amazonses.com
```

**Note**: The actual values will be different - AWS generates unique tokens for your domain.

---

## Step 2: Add DNS Records to Vercel

Since your DNS is managed by Vercel, you have **two options**:

### Option A: Via Vercel Dashboard (Recommended)

1. **Go to**: https://vercel.com/dashboard
2. **Select your project**: suoops-frontend
3. **Click "Settings"** → **"Domains"**
4. **Click on "suoops.com"** → **"Manage"**
5. **Scroll to DNS Records**
6. **Add each CNAME record** from SES:
   - Click "Add Record"
   - Type: CNAME
   - Name: `abc123def._domainkey` (without .suoops.com)
   - Value: `abc123def.dkim.amazonses.com`
   - Repeat for all 3 DKIM records

### Option B: Via Vercel CLI

```bash
# DKIM Record 1
vercel dns add suoops.com abc123def._domainkey CNAME abc123def.dkim.amazonses.com

# DKIM Record 2
vercel dns add suoops.com xyz789ghi._domainkey CNAME xyz789ghi.dkim.amazonses.com

# DKIM Record 3
vercel dns add suoops.com jkl456mno._domainkey CNAME jkl456mno.dkim.amazonses.com
```

**Replace** `abc123def`, `xyz789ghi`, `jkl456mno` with your actual DKIM tokens from AWS.

---

## Step 3: Verify Domain Status

### Wait for Verification (5-10 minutes)

1. **Go back to SES Console**: https://console.aws.amazon.com/ses/
2. **Click "Verified identities"**
3. **Click on "suoops.com"**
4. **Check "Identity status"**:
   - Pending → Verification in progress
   - Verified → ✅ Ready to send emails!

### Verify DNS Records (Optional)

```bash
# Check DKIM record 1
dig abc123def._domainkey.suoops.com CNAME

# Check DKIM record 2
dig xyz789ghi._domainkey.suoops.com CNAME

# Check DKIM record 3
dig jkl456mno._domainkey.suoops.com CNAME
```

---

## Step 4: Create SMTP Credentials

### 4.1 Create IAM User for SMTP

1. **Still in SES Console**: https://console.aws.amazon.com/ses/
2. **Click "SMTP Settings"** (left sidebar)
3. **Scroll down** to "SMTP credentials"
4. **Click "Create SMTP credentials"**
5. **IAM User Name**: `suoops-ses-smtp-user`
6. **Click "Create user"**

### 4.2 Save SMTP Credentials

You'll see:
```
SMTP Username: AKIAIOSFODNN7EXAMPLE
SMTP Password: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**⚠️ IMPORTANT**: Copy both values immediately - you won't see the password again!

### 4.3 SMTP Endpoint Details

For `eu-north-1`:
```
SMTP Host: email-smtp.eu-north-1.amazonaws.com
SMTP Port: 587 (TLS/STARTTLS)
SMTP Port: 465 (SSL) - alternative
```

---

## Step 5: Request Production Access

### Why?

By default, SES is in **Sandbox mode**:
- ❌ Can only send to verified email addresses
- ❌ Limit: 200 emails/day
- ❌ 1 email per second

Production mode removes these limits:
- ✅ Send to any email address
- ✅ 50,000 emails/day (can request increase)
- ✅ 14 emails per second

### How to Request:

1. **SES Console**: https://console.aws.amazon.com/ses/
2. **Click "Account dashboard"** (left sidebar)
3. **Scroll to "Sending limits"**
4. **Click "Request production access"**
5. **Fill out the form**:
   - **Use case**: Transactional
   - **Website URL**: https://suoops.com
   - **Description**: 
     ```
     SuoOps is an invoice and payroll management system for small businesses in Nigeria.
     We send transactional emails including:
     - Invoice receipts to customers
     - Payment confirmations
     - Password reset emails
     - System notifications
     
     Expected volume: ~500 emails/day
     Bounce rate: <2%
     Complaint rate: <0.1%
     ```
   - **Compliance**: Describe how you handle bounces/complaints
6. **Submit request**

**Processing time**: 24 hours (usually faster)

---

## Step 6: Configure Heroku Environment Variables

Once domain is verified and SMTP credentials are created:

```bash
heroku config:set \
  SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com \
  SES_SMTP_PORT=587 \
  SES_SMTP_USER=<your-smtp-username> \
  SES_SMTP_PASSWORD=<your-smtp-password> \
  FROM_EMAIL=noreply@suoops.com \
  -a suoops-backend
```

**Alternative sender addresses**:
- `noreply@suoops.com` - Generic notifications
- `invoices@suoops.com` - Invoice-related emails
- `support@suoops.com` - Customer support

---

## Step 7: Test Email Sending

### Test via Python Script

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# SMTP Configuration
SMTP_HOST = "email-smtp.eu-north-1.amazonaws.com"
SMTP_PORT = 587
SMTP_USER = "your-smtp-username"
SMTP_PASSWORD = "your-smtp-password"
FROM_EMAIL = "noreply@suoops.com"

# Create message
msg = MIMEMultipart()
msg['From'] = FROM_EMAIL
msg['To'] = "your-email@example.com"  # Change to your email
msg['Subject'] = "Test Email from SuoOps"

body = """
Hello!

This is a test email from SuoOps to verify Amazon SES configuration.

If you received this, email sending is working correctly!

Best regards,
SuoOps Team
"""
msg.attach(MIMEText(body, 'plain'))

# Send email
try:
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Failed to send email: {e}")
```

### Test via cURL (Alternative)

```bash
curl -X POST https://api.suoops.com/test-email \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"to":"your-email@example.com","subject":"Test","body":"Hello!"}'
```

---

## Step 8: Monitor Email Activity

### SES Console Monitoring

1. **Go to SES Console**: https://console.aws.amazon.com/ses/
2. **Click "Account dashboard"**
3. **View metrics**:
   - Emails sent
   - Bounce rate
   - Complaint rate
   - Delivery rate

### CloudWatch Metrics

SES automatically publishes metrics to CloudWatch:
- `Send` - Total emails sent
- `Delivery` - Successfully delivered
- `Bounce` - Bounced emails
- `Complaint` - Spam complaints
- `Reject` - Rejected by SES

---

## Pricing Estimate

### Free Tier
- **First 62,000 emails/month**: FREE (when sent from EC2)
- **From other services (Heroku)**: $0.10 per 1,000 emails

### Expected Costs (from Heroku)
- **100 emails/day** = 3,000/month = **$0.30/month**
- **500 emails/day** = 15,000/month = **$1.50/month**
- **1,000 emails/day** = 30,000/month = **$3.00/month**

---

## Troubleshooting

### Domain Not Verifying

**Problem**: Domain status stuck on "Pending"

**Solutions**:
1. Check DNS records are correct (no typos)
2. Wait 10-15 minutes for DNS propagation
3. Verify with `dig` command
4. Check Vercel DNS dashboard

### SMTP Authentication Failed

**Problem**: `535 Authentication failed`

**Solutions**:
1. Double-check SMTP username and password
2. Ensure using correct region endpoint
3. Verify IAM user has SES send permissions
4. Try regenerating SMTP credentials

### Emails Not Sending

**Problem**: No errors but emails not received

**Solutions**:
1. Check spam folder
2. Verify domain is "Verified" in SES
3. Check SES account is out of sandbox mode
4. Review SES sending statistics for bounces
5. Verify FROM_EMAIL matches verified domain

### High Bounce Rate

**Problem**: Many emails bouncing

**Solutions**:
1. Validate email addresses before sending
2. Remove hard bounces from list
3. Use email verification service
4. Check email content for spam triggers

---

## Security Best Practices

1. **Never commit credentials** to git
2. **Use environment variables** for all secrets
3. **Rotate SMTP credentials** every 90 days
4. **Monitor bounce/complaint rates** daily
5. **Implement email verification** for user signups
6. **Use TLS/STARTTLS** for SMTP connections
7. **Set up SPF records** (optional but recommended)
8. **Enable DMARC** for additional security

### SPF Record (Optional)

Add to Vercel DNS:
```
Type: TXT
Name: suoops.com
Value: v=spf1 include:amazonses.com ~all
```

---

## Next Steps

1. ✅ Verify domain in SES
2. ✅ Add DNS records to Vercel
3. ✅ Wait for verification (5-10 min)
4. ✅ Create SMTP credentials
5. ✅ Configure Heroku environment
6. ✅ Test email sending
7. ⏳ Request production access (optional, takes 24h)
8. ✅ Monitor email metrics

---

## Support Resources

- **AWS SES Documentation**: https://docs.aws.amazon.com/ses/
- **SES Sandbox Exit**: https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html
- **SMTP Settings**: https://docs.aws.amazon.com/ses/latest/dg/smtp-credentials.html
- **Vercel DNS**: https://vercel.com/docs/concepts/projects/custom-domains

---

**Ready to start?** Follow the steps above and let me know if you need help with any step!
