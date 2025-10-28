# Amazon SES Setup Guide for SuoPay

This guide will help you set up Amazon SES (Simple Email Service) for sending unlimited emails at low cost (₦400 per 10,000 emails).

## Why Amazon SES?

- ✅ **Cost-effective:** Only ₦40 per 1,000 emails (vs Gmail's 500/day limit)
- ✅ **No daily limits:** Scale to millions of emails
- ✅ **High deliverability:** 99%+ delivery rate
- ✅ **Already on AWS:** Same billing as your S3 bucket
- ✅ **Professional:** Proper email infrastructure

---

## Prerequisites

- ✅ AWS Account (you already have one for S3)
- ✅ Domain name (suoops.com)
- ✅ Access to DNS settings (Namecheap, GoDaddy, Cloudflare, etc.)

---

## Step 1: Request Production Access (Most Important!)

Amazon SES starts in **sandbox mode** which only allows:
- 200 emails per day
- Only to verified email addresses

You need to request production access to send to any email address.

### Request Production Access

1. **Go to AWS SES Console:**
   - URL: https://console.aws.amazon.com/ses/
   - Region: Select **eu-north-1** (Europe - Stockholm) - same as your S3 bucket

2. **Click "Get Set Up" or "Request production access"**
   - Look for the banner at the top or in the left sidebar

3. **Fill out the form:**

   **Use Case:**
   - **Mail type:** Transactional
   - **Website URL:** https://suoops.com
   - **Use case description:**
   ```
   SuoPay is an invoice management SaaS platform for small businesses in Nigeria.
   We send transactional invoice notifications to customers when invoices are created.
   Emails contain:
   - Invoice details (amount, due date, items)
   - PDF invoice attachment
   - Payment instructions
   
   We do NOT send marketing emails or bulk campaigns.
   All recipients have a business relationship with our users.
   ```

   **Additional Information:**
   - **Will you send to acquired/rented lists?** No
   - **How do you maintain your mailing list?**
   ```
   Email addresses are provided by our users (business owners) for their customers.
   Each email is one-to-one transactional communication.
   We only send invoices to customers who have purchased goods/services.
   ```
   
   - **How do you handle bounces and complaints?**
   ```
   - We validate email format before sending
   - We monitor bounce rates via SES metrics
   - We automatically suppress invalid addresses
   - Unsubscribe option in every email
   - Manual complaint review and removal
   - Target <5% bounce rate, <0.1% complaint rate
   ```
   
   - **Expected sending volume:**
   ```
   Current: 100-500 emails/day
   3 months: 1,000 emails/day
   6 months: 5,000 emails/day
   12 months: 10,000 emails/day
   ```

4. **Submit and wait:**
   - Usually approved within **24-48 hours**
   - Check your email for approval notification
   - AWS may ask follow-up questions

---

## Step 2: Verify Your Domain (Recommended)

Verifying your domain (suoops.com) improves deliverability and allows you to send from any email address @suoops.com.

### 2.1 Start Domain Verification

1. Go to **SES Console → Identities**
2. Click **"Create identity"**
3. Select **"Domain"**
4. Enter: `suoops.com`
5. Check **"Use a default DKIM signing key"**
6. Click **"Create identity"**

### 2.2 Add DNS Records

AWS will show you 3 DKIM records and 1 SPF record. Add these to your DNS provider.

#### For Namecheap, GoDaddy, Cloudflare:

**DKIM Records (3 records):**
```
Type: CNAME
Name: abcd1234._domainkey.suoops.com
Value: abcd1234.dkim.amazonses.com
TTL: Automatic

Type: CNAME
Name: efgh5678._domainkey.suoops.com
Value: efgh5678.dkim.amazonses.com
TTL: Automatic

Type: CNAME
Name: ijkl9012._domainkey.suoops.com
Value: ijkl9012.dkim.amazonses.com
TTL: Automatic
```

**Note:** AWS will show you the actual values - copy them exactly!

**Mail FROM Domain (Optional but recommended):**
```
Type: MX
Name: mail.suoops.com
Value: 10 feedback-smtp.eu-north-1.amazonses.com
TTL: Automatic

Type: TXT
Name: mail.suoops.com
Value: "v=spf1 include:amazonses.com ~all"
TTL: Automatic
```

### 2.3 Wait for Verification

- DNS propagation takes **15 minutes to 48 hours**
- Check status in SES Console → Identities → suoops.com
- Status will change from "Pending" to "Verified"

**Check DNS propagation:**
```bash
# Check DKIM records
dig abcd1234._domainkey.suoops.com CNAME

# Check MX record
dig mail.suoops.com MX
```

---

## Step 3: Create SMTP Credentials

1. Go to **SES Console → SMTP Settings**
2. Click **"Create SMTP credentials"**
3. **IAM User Name:** `suopay-smtp-user`
4. Click **"Create user"**

5. **IMPORTANT:** Save the credentials shown on next screen:
   ```
   SMTP Username: AKIAIOSFODNN7EXAMPLE
   SMTP Password: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
   ```
   
   ⚠️ **Save these immediately!** They are shown only once.

6. **SMTP Server details:**
   ```
   Host: email-smtp.eu-north-1.amazonaws.com
   Port: 587 (TLS)
   Region: eu-north-1 (Europe - Stockholm)
   ```

---

## Step 4: Configure Heroku with SES Credentials

```bash
# Set email provider to SES
heroku config:set \
  EMAIL_PROVIDER=ses \
  --app suoops-backend

# Set SES SMTP credentials
heroku config:set \
  SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com \
  SES_SMTP_PORT=587 \
  SES_SMTP_USER=AKIAIOSFODNN7EXAMPLE \
  SES_SMTP_PASSWORD=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  SES_REGION=eu-north-1 \
  --app suoops-backend

# Optional: Update FROM_EMAIL to use your domain
heroku config:set \
  FROM_EMAIL=invoices@suoops.com \
  --app suoops-backend
```

**Check configuration:**
```bash
heroku config --app suoops-backend | grep -E "EMAIL|SES|SMTP"
```

---

## Step 5: Test Email Sending

### Test in Sandbox Mode (while waiting for production approval)

While waiting for production access, you can test with verified email addresses:

1. **Verify test email:**
   - SES Console → Identities → Create identity
   - Select "Email address"
   - Enter your email: `ayibatonyeikemike9@gmail.com`
   - Check your inbox for verification email
   - Click verification link

2. **Test sending:**
```bash
curl -X POST https://suoops-backend.herokuapp.com/invoices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "customer_name": "Test Customer",
    "customer_email": "ayibatonyeikemike9@gmail.com",
    "amount": 10000,
    "lines": [{"description": "Test Item", "quantity": 1, "unit_price": 10000}]
  }'
```

3. **Check inbox** (including spam folder)

### Test After Production Approval

Once production access is approved, test with any email:

```bash
curl -X POST https://suoops-backend.herokuapp.com/invoices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "customer_name": "Any Customer",
    "customer_email": "anycustomer@example.com",
    "amount": 50000,
    "lines": [{"description": "Website Design", "quantity": 1, "unit_price": 50000}]
  }'
```

---

## Step 6: Monitor Email Sending

### Check Heroku Logs
```bash
# Watch email sending in real-time
heroku logs --tail --app suoops-backend | grep -i "email\|ses"

# Check for errors
heroku logs --tail --app suoops-backend | grep -i "error.*email"
```

### Check SES Console

1. Go to **SES Console → Reputation metrics**
2. Monitor:
   - **Sends:** Total emails sent
   - **Bounces:** Invalid email addresses (<5% is good)
   - **Complaints:** Spam reports (<0.1% is good)
   - **Delivery rate:** Should be >95%

3. **Set up CloudWatch alarms** (optional):
   - Alert when bounce rate >5%
   - Alert when complaint rate >0.1%
   - Alert on sending quota reached

---

## Cost Management

### Current Pricing (as of Oct 2025)
- **Sending:** $0.10 per 1,000 emails (~₦40)
- **Receiving:** $0 (not using)
- **Attachments:** Included in sending cost

### Example Costs
| Emails/Month | Cost USD | Cost NGN |
|--------------|----------|----------|
| 1,000 | $0.10 | ₦40 |
| 10,000 | $1.00 | ₦400 |
| 50,000 | $5.00 | ₦2,000 |
| 100,000 | $10.00 | ₦4,000 |

### Set Spending Limits
```bash
# Set AWS Budget alert
aws budgets create-budget \
  --account-id YOUR_ACCOUNT_ID \
  --budget file://ses-budget.json
```

**ses-budget.json:**
```json
{
  "BudgetName": "SES-Monthly-Budget",
  "BudgetLimit": {
    "Amount": "5.00",
    "Unit": "USD"
  },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
```

---

## Troubleshooting

### Issue: "Email address not verified"
**Solution:** 
- You're still in sandbox mode
- Verify the recipient email in SES Console
- Or wait for production access approval

### Issue: "Message rejected: Email address is not verified"
**Solution:**
```bash
# Check if production access approved
aws sesv2 get-account --region eu-north-1 | grep ProductionAccessEnabled

# If false, check your support case or resubmit request
```

### Issue: "Daily sending quota exceeded"
**Solution:**
- You're in sandbox mode (200/day limit)
- Request production access
- Or verify you were approved and check quota:
```bash
aws ses get-send-quota --region eu-north-1
```

### Issue: Emails going to spam
**Solutions:**
1. **Verify domain** with DKIM (improves trust)
2. **Set up SPF record:**
   ```
   Type: TXT
   Name: suoops.com
   Value: "v=spf1 include:amazonses.com ~all"
   ```
3. **Add DMARC record:**
   ```
   Type: TXT
   Name: _dmarc.suoops.com
   Value: "v=DMARC1; p=quarantine; rua=mailto:dmarc@suoops.com"
   ```
4. **Warm up domain** (gradually increase volume)
5. **Monitor bounce/complaint rates** (keep low)

### Issue: High bounce rate
**Solution:**
```python
# Add email validation before sending
from email_validator import validate_email, EmailNotValidError

try:
    valid = validate_email(email)
    email = valid.email  # Normalized form
except EmailNotValidError as e:
    logger.warning(f"Invalid email: {email} - {e}")
    return False
```

### Issue: SMTP authentication failed
**Solution:**
- Check SMTP credentials are correct
- Verify region matches (eu-north-1)
- Check Heroku config vars are set
```bash
heroku config:get SES_SMTP_USER --app suoops-backend
heroku config:get SES_SMTP_PASSWORD --app suoops-backend
```

---

## Switch Between Gmail and SES

Your code now supports both providers. Switch easily:

### Use Gmail (default, 500/day)
```bash
heroku config:set EMAIL_PROVIDER=gmail --app suoops-backend
```

### Use Amazon SES (unlimited)
```bash
heroku config:set EMAIL_PROVIDER=ses --app suoops-backend
```

### Check current provider
```bash
heroku config:get EMAIL_PROVIDER --app suoops-backend
```

---

## Production Checklist

Before going live with SES:

- [ ] Production access approved
- [ ] Domain verified (DKIM records added)
- [ ] SMTP credentials created and saved
- [ ] Heroku configured with SES credentials
- [ ] FROM_EMAIL set to your domain (@suoops.com)
- [ ] Test emails sent successfully
- [ ] Emails not going to spam
- [ ] Monitoring set up (CloudWatch/logs)
- [ ] Bounce/complaint handling configured
- [ ] Spending limits set in AWS Budget

---

## Advanced Features

### Email Templates (Future Enhancement)

```python
# app/services/notification_service.py

async def send_invoice_email_templated(self, invoice, recipient_email):
    """Send using SES templates for better performance"""
    client = boto3.client('ses', region_name=settings.SES_REGION)
    
    response = client.send_templated_email(
        Source=settings.FROM_EMAIL,
        Destination={'ToAddresses': [recipient_email]},
        Template='InvoiceNotification',
        TemplateData=json.dumps({
            'invoiceId': invoice.invoice_id,
            'amount': invoice.amount,
            'customerName': invoice.customer.name
        })
    )
```

### Webhook for Bounces/Complaints

```python
# app/api/routes_webhooks.py

@router.post("/webhooks/ses")
async def handle_ses_webhook(request: Request):
    """Handle SES bounce/complaint notifications"""
    data = await request.json()
    
    if data.get('Type') == 'Notification':
        message = json.loads(data['Message'])
        
        if message.get('notificationType') == 'Bounce':
            # Handle bounce - mark email as invalid
            email = message['bounce']['bouncedRecipients'][0]['emailAddress']
            logger.warning(f"Email bounced: {email}")
            # Add to suppression list
            
        elif message.get('notificationType') == 'Complaint':
            # Handle complaint - user marked as spam
            email = message['complaint']['complainedRecipients'][0]['emailAddress']
            logger.error(f"Spam complaint: {email}")
            # Unsubscribe user
    
    return {"status": "ok"}
```

---

## Support

### AWS Support Resources
- **SES Console:** https://console.aws.amazon.com/ses/
- **Documentation:** https://docs.aws.amazon.com/ses/
- **Pricing:** https://aws.amazon.com/ses/pricing/
- **Support:** https://console.aws.amazon.com/support/

### Check Request Status
1. Go to AWS Support Center: https://console.aws.amazon.com/support/
2. Look for your SES production access case
3. Check status and any questions from AWS

### Common Questions from AWS

**Q: What type of emails will you send?**
A: Transactional invoices only, no marketing

**Q: How do you get email addresses?**
A: Business owners provide their customers' emails

**Q: How do you handle unsubscribes?**
A: We include unsubscribe option in all emails

---

## Migration Timeline

### Week 1: Setup
- [ ] Request production access
- [ ] Verify domain (add DNS records)
- [ ] Create SMTP credentials
- [ ] Configure Heroku

### Week 2: Testing
- [ ] Test in sandbox with verified emails
- [ ] Wait for production approval
- [ ] Test with any email address
- [ ] Monitor deliverability

### Week 3: Gradual Rollout
- [ ] Send 10% of emails via SES
- [ ] Monitor metrics (bounce, complaint)
- [ ] Increase to 50% if stable
- [ ] Compare with Gmail performance

### Week 4: Full Migration
- [ ] Route 100% traffic to SES
- [ ] Keep Gmail as fallback
- [ ] Monitor costs
- [ ] Optimize sending patterns

---

## Best Practices

1. **Warm up your domain:**
   - Start: 100 emails/day
   - Week 2: 500 emails/day
   - Week 3: 1,000 emails/day
   - Week 4+: Unlimited

2. **Monitor metrics:**
   - Bounce rate <5%
   - Complaint rate <0.1%
   - Delivery rate >95%

3. **Email validation:**
   - Check format before sending
   - Use email-validator library
   - Suppress invalid addresses

4. **Content quality:**
   - Clear subject lines
   - Professional formatting
   - Unsubscribe option
   - No spam words

5. **Infrastructure:**
   - Use DKIM (verify domain)
   - Set up SPF records
   - Add DMARC policy
   - Monitor reputation

---

**Next Steps:** Request production access now! It takes 24-48 hours for approval.

Last updated: October 22, 2025
