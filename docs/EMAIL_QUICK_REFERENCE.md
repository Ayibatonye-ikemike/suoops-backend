# Quick Reference: Email System

## Current Setup (October 22, 2025)

✅ **Active Provider:** Gmail SMTP  
✅ **Limit:** 500 emails per day (15,000/month)  
✅ **Cost:** Free  
✅ **Status:** Fully configured and working  

---

## When to Upgrade to Amazon SES

Upgrade when:
- ✅ Consistently sending >400 emails/day
- ✅ Need unlimited daily sending
- ✅ Want to save costs at scale (₦400 per 10k emails)
- ✅ Need better analytics and monitoring

---

## Switch Email Provider (Easy!)

### Check Current Provider
```bash
heroku config:get EMAIL_PROVIDER --app suoops-backend
# Output: gmail
```

### Use Gmail (Current - 500/day)
```bash
heroku config:set EMAIL_PROVIDER=gmail --app suoops-backend
```

### Use Amazon SES (After setup - Unlimited)
```bash
heroku config:set EMAIL_PROVIDER=ses --app suoops-backend
```

**That's it!** No code changes needed. Just change one environment variable.

---

## Amazon SES Setup (When Ready)

### Step 1: Request Production Access (Start Today!)
⏱️ Takes **24-48 hours** for approval

1. Go to: https://console.aws.amazon.com/ses/
2. Select region: **eu-north-1** (Stockholm - same as your S3)
3. Click **"Request production access"**
4. Fill form (see `docs/amazon-ses-setup.md` for exact wording)
5. Submit and wait for email approval

**What to say in the form:**
- **Use case:** Transactional invoice notifications for SaaS platform
- **Volume:** Starting at 500/day, growing to 5,000/day
- **Email type:** One-to-one invoices, not bulk marketing
- **Bounce handling:** Email validation, monitoring, automatic suppression

### Step 2: Verify Domain (While Waiting)
⏱️ Takes **15 minutes - 48 hours** for DNS propagation

1. SES Console → Identities → Create identity → Domain
2. Enter: `suoops.com`
3. AWS shows you 3 DKIM records
4. Add them to your DNS (Namecheap/GoDaddy/Cloudflare):

```
Type: CNAME
Name: abcd1234._domainkey.suoops.com
Value: abcd1234.dkim.amazonses.com

Type: CNAME  
Name: efgh5678._domainkey.suoops.com
Value: efgh5678.dkim.amazonses.com

Type: CNAME
Name: ijkl9012._domainkey.suoops.com
Value: ijkl9012.dkim.amazonses.com
```

### Step 3: Create SMTP Credentials (After Approval)
⏱️ Takes **5 minutes**

1. SES Console → SMTP Settings
2. Create SMTP credentials
3. Name: `suopay-smtp-user`
4. **Save the username and password immediately!** (shown only once)

### Step 4: Configure Heroku (Final Step)
⏱️ Takes **2 minutes**

```bash
# Set SES credentials
heroku config:set \
  SES_SMTP_USER=AKIAIOSFODNN7EXAMPLE \
  SES_SMTP_PASSWORD=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  --app suoops-backend

# Switch to SES
heroku config:set EMAIL_PROVIDER=ses --app suoops-backend

# Optional: Use your domain for FROM address
heroku config:set FROM_EMAIL=invoices@suoops.com --app suoops-backend
```

### Step 5: Test It! 
```bash
# Create invoice with email
curl -X POST https://suoops-backend.herokuapp.com/invoices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "customer_name": "Test Customer",
    "customer_email": "test@example.com",
    "amount": 10000,
    "lines": [{"description": "Test", "quantity": 1, "unit_price": 10000}]
  }'

# Check logs
heroku logs --tail --app suoops-backend | grep -i "email\|ses"
```

**Expected log output:**
```
Using Amazon SES for email: email-smtp.eu-north-1.amazonaws.com
Sending email via Amazon SES to test@example.com
Sent invoice email to test@example.com for invoice INV-...
```

---

## Cost Comparison

### Gmail (Current)
- **Cost:** Free
- **Limit:** 500 emails/day
- **Good for:** Getting started, <10,000 emails/month
- **Status:** ✅ Working now

### Amazon SES (After setup)
- **Cost:** ₦40 per 1,000 emails
- **Limit:** Unlimited (after production approval)
- **Good for:** Scaling beyond 500/day
- **Setup time:** 2-3 days total

### Example Costs

| Emails/Month | Gmail | Amazon SES |
|--------------|-------|------------|
| 5,000 | ✅ Free | ₦200 |
| 10,000 | ✅ Free | ₦400 |
| 15,000 | ❌ Over limit | ₦600 |
| 50,000 | ❌ Over limit | ₦2,000 |
| 100,000 | ❌ Over limit | ₦4,000 |

**Gmail is perfect until you hit 400+ emails/day!**

---

## Monitoring

### Check Email Usage
```bash
# See all email logs
heroku logs --tail --app suoops-backend | grep -i "email"

# Count emails sent today (approximate)
heroku logs --app suoops-backend | grep "Sent invoice email" | wc -l

# Check which provider is active
heroku config:get EMAIL_PROVIDER --app suoops-backend
```

### Monitor SES (After switching)
```bash
# Check sending quota
aws ses get-send-quota --region eu-north-1

# Check reputation (bounce/complaint rates)
aws sesv2 get-account --region eu-north-1
```

---

## Troubleshooting

### Gmail Not Sending
```bash
# Check credentials configured
heroku config --app suoops-backend | grep SMTP

# Check logs for errors
heroku logs --tail --app suoops-backend | grep -i "smtp\|email.*error"

# Verify App Password is correct
# Go to: https://myaccount.google.com/apppasswords
```

### SES Not Sending (After switching)
```bash
# Check SES credentials
heroku config --app suoops-backend | grep SES

# Check production access approved
aws sesv2 get-account --region eu-north-1 | grep ProductionAccessEnabled
# Should show: true

# Check domain verified
aws sesv2 get-email-identity --email-identity suoops.com --region eu-north-1
# Should show: VerificationStatus: SUCCESS
```

### Emails Going to Spam
1. ✅ Verify domain with DKIM (improves trust)
2. ✅ Add SPF record: `v=spf1 include:amazonses.com ~all`
3. ✅ Warm up domain gradually (start with 100/day, increase weekly)
4. ✅ Monitor bounce/complaint rates (<5% and <0.1%)

---

## Timeline for SES Migration

### Week 1: Start Process
- **Day 1:** Request SES production access
- **Day 1:** Add DNS records for domain verification
- **Day 2-3:** Wait for production approval email

### Week 2: Setup
- **Day 4:** Create SMTP credentials
- **Day 4:** Configure Heroku with SES credentials
- **Day 5:** Test sending in sandbox mode (to verified emails)
- **Day 5-7:** Wait for domain verification (DNS propagation)

### Week 3: Testing
- **Day 8:** Domain verified ✅
- **Day 8:** Test sending to any email (production mode)
- **Day 9-14:** Send 10% of emails via SES, monitor metrics

### Week 4: Full Migration
- **Day 15:** Route 50% traffic to SES
- **Day 17:** Route 100% traffic to SES
- **Day 18+:** Monitor costs, deliverability, keep Gmail as backup

---

## Key Heroku Config Variables

```bash
# Current Gmail Setup (v49)
EMAIL_PROVIDER=gmail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=<your-gmail-app-password>
FROM_EMAIL=noreply@suoops.com

# Future SES Setup (add when ready)
SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com
SES_SMTP_PORT=587
SES_SMTP_USER=(create in step 3)
SES_SMTP_PASSWORD=(create in step 3)
SES_REGION=eu-north-1
```

---

## Support Resources

- **Gmail SMTP:** `docs/email-setup.md`
- **Amazon SES:** `docs/amazon-ses-setup.md`
- **Provider Comparison:** `docs/email-providers-comparison.md`
- **Production Checklist:** `docs/PRODUCTION_READY.md`

---

## Quick Commands

```bash
# Check current provider
heroku config:get EMAIL_PROVIDER --app suoops-backend

# Switch to Gmail
heroku config:set EMAIL_PROVIDER=gmail --app suoops-backend

# Switch to SES (after setup)
heroku config:set EMAIL_PROVIDER=ses --app suoops-backend

# View email logs
heroku logs --tail --app suoops-backend | grep -i "email"

# Test email sending
./test-production.sh

# Check all email-related config
heroku config --app suoops-backend | grep -E "EMAIL|SMTP|SES|FROM"
```

---

## Decision Flowchart

```
Are you sending >400 emails/day?
│
├─ NO  → Stay on Gmail (free, simple)
│        ✅ You're good until 400/day!
│
└─ YES → Upgrade to Amazon SES
         │
         ├─ Already sent 400+ today?
         │  └─ URGENT: Request SES access now (24-48h approval)
         │
         └─ Consistently approaching 400/day?
            └─ Start SES setup this week (proactive)
```

---

## Summary

**Right now:**
- ✅ Gmail is working perfectly
- ✅ You can send 500 emails/day
- ✅ Completely free
- ✅ No action needed

**When you're ready to scale:**
1. Request SES production access (takes 2-3 days)
2. Add DNS records
3. Get SMTP credentials
4. Configure Heroku with SES credentials
5. Switch: `heroku config:set EMAIL_PROVIDER=ses`

**Questions?** Check the full guide: `docs/amazon-ses-setup.md`

Last updated: October 22, 2025  
Heroku: v49  
Provider: Gmail (500/day)
