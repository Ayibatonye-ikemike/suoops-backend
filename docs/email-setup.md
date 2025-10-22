# Email Configuration Guide (SMTP)

## Recommended: Gmail SMTP (Best for Nigeria)

Gmail SMTP is reliable, free, and works great internationally including Nigeria.

### Step 1: Enable 2-Step Verification on Gmail

1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** if not already enabled

### Step 2: Create App Password

1. Go to https://myaccount.google.com/apppasswords
2. Select:
   - **App:** Mail
   - **Device:** Other (Custom name) → Type "SuoPay"
3. Click **Generate**
4. Copy the 16-character password (no spaces)

**Example:** `abcd efgh ijkl mnop` → Use as: `abcdefghijklmnop`

### Step 3: Configure Environment Variables

Add these to your `.env` file:

```bash
# Gmail SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop  # App password from step 2
FROM_EMAIL=noreply@suopay.io  # Optional: Custom sender name
```

### Step 4: Configure Heroku

Run this command (replace with your actual values):

```bash
heroku config:set \
  SMTP_HOST=smtp.gmail.com \
  SMTP_PORT=587 \
  SMTP_USER=your-email@gmail.com \
  SMTP_PASSWORD=your-app-password \
  FROM_EMAIL=noreply@suopay.io \
  --app suopay-backend
```

---

## Alternative: Brevo (Sendinblue)

Brevo works excellently in Nigeria with 300 free emails/day.

### Step 1: Create Brevo Account

1. Sign up at https://www.brevo.com/
2. Verify your account

### Step 2: Get SMTP Credentials

1. Go to https://app.brevo.com/settings/keys/smtp
2. Copy:
   - SMTP Server: `smtp-relay.brevo.com`
   - Port: `587`
   - Login: Your email
   - SMTP Key: Generate new key

### Step 3: Configure Environment Variables

```bash
# Brevo SMTP Configuration
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-smtp-key-from-brevo
FROM_EMAIL=noreply@suopay.io
```

---

## Alternative: Zoho Mail (Also works in Nigeria)

Free tier: 5GB storage, works globally

### SMTP Settings:

```bash
SMTP_HOST=smtp.zoho.com
SMTP_PORT=587
SMTP_USER=your-email@zohomail.com
SMTP_PASSWORD=your-password
FROM_EMAIL=noreply@suopay.io
```

---

## Testing Email Configuration

After configuring, test with this curl command:

```bash
# Get your access token first
curl -X POST https://api.suopay.io/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"+2348012345678","password":"yourpassword"}'

# Create invoice with email (replace TOKEN)
curl -X POST https://api.suopay.io/invoices \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Test Customer",
    "customer_email": "test@example.com",
    "amount": 10000,
    "lines": [{"description": "Test Service", "quantity": 1, "unit_price": 10000}]
  }'
```

Check your email logs:
```bash
heroku logs --tail --app suopay-backend | grep -i email
```

---

## Limits Comparison

| Provider | Free Tier | Best For | Works in Nigeria |
|----------|-----------|----------|------------------|
| **Gmail** | 500 emails/day | Small business, testing | ✅ Yes |
| **Brevo** | 300 emails/day | Medium business | ✅ Yes |
| **SendGrid** | 100 emails/day | High volume (if accessible) | ⚠️ Sometimes blocked |
| **Zoho** | 5GB storage | Professional email | ✅ Yes |

---

## Recommended Setup for SuoPay

**For Testing/Development:**
- Use **Gmail** with your personal email
- Quick setup, reliable

**For Production:**
- Use **Brevo** (300 emails/day free)
- Better deliverability
- Professional features

---

## Troubleshooting

### Issue: "Authentication failed"
**Solution:** 
- Gmail: Make sure you're using App Password, not regular password
- Brevo: Verify SMTP key is correct

### Issue: "Connection refused"
**Solution:** 
- Check SMTP_PORT is 587 (not 465 or 25)
- Verify SMTP_HOST is correct

### Issue: Emails not received
**Solution:**
- Check spam folder
- Verify FROM_EMAIL is a valid address
- Check Heroku logs for errors

### Issue: "535 Authentication failed"
**Solution:**
- Gmail: Enable "Less secure app access" (not recommended) OR use App Password
- Verify credentials are correct

---

## Security Best Practices

✅ **Use App Passwords** (Gmail) - never use main account password
✅ **Store credentials in environment variables** - never commit to git
✅ **Use TLS/STARTTLS** - Port 587 (already configured)
✅ **Monitor usage** - Check for unusual activity
✅ **Rotate passwords** - Change every 90 days

---

## Current Configuration Status

- ✅ SMTP code implemented in NotificationService
- ✅ Email field added to invoice schema
- ✅ Frontend form includes email input
- ⏳ SMTP credentials needed (see above)
- ⏳ Test email delivery

---

## Next Steps

1. ✅ Choose email provider (Gmail recommended for Nigeria)
2. ✅ Get SMTP credentials
3. ✅ Add to `.env` file locally
4. ✅ Configure Heroku with credentials
5. ✅ Test invoice email delivery
6. ✅ Monitor email logs

**Estimated setup time:** 5-10 minutes

