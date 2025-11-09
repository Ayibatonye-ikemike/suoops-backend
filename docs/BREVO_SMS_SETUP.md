# Brevo (Sendinblue) SMS Setup Guide

## Overview
You're already using Brevo for email! Now you can add SMS to the same account for seamless multi-channel notifications.

## Why Use Brevo for SMS?

✅ **Already integrated** - You're using Brevo for email  
✅ **Single platform** - Manage email + SMS in one dashboard  
✅ **Competitive pricing** - Similar to other providers  
✅ **Easy setup** - Just add SMS credits  
✅ **Reliable** - European provider with global reach  

## Step 1: Get SMS API Key

### Option 1: Use Existing Email API Key
Your current Brevo account might already have SMS enabled. Try using your existing API key first.

### Option 2: Generate New SMS API Key
1. Log in to https://app.brevo.com
2. Go to **Settings** → **API Keys**
3. Click "Generate a new API key"
4. Name it: `SuoOps SMS`
5. Copy the key (starts with `xkeysib-...`)

## Step 2: Buy SMS Credits

1. In Brevo dashboard, go to **SMS** → **Buy Credits**
2. Choose your plan:
   - **Pay as you go**: No monthly fee
   - **Credits**: Buy in bulk for discounts

### Pricing (Nigeria):
- **₦3-5 per SMS** (approximately)
- Varies by destination network
- Check latest prices in Brevo dashboard

### Recommended Starting Amount:
- **500 SMS credits** = ~₦2,000-2,500
- Enough to test and handle initial customers

## Step 3: Configure Sender Name

1. Go to **SMS** → **Senders**
2. Add sender name: `SuoOps`
3. This appears as the sender on customer phones

**Note**: Some countries require sender name approval. Nigeria typically allows alphanumeric sender names without pre-approval.

## Step 4: Set Heroku Environment Variables

```bash
# Required: Brevo API Key for SMS
heroku config:set BREVO_API_KEY=xkeysib-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx --app suoops-backend

# Optional: Custom sender name (default is "SuoOps")
heroku config:set BREVO_SENDER_NAME=SuoOps --app suoops-backend

# Set SMS provider to Brevo
heroku config:set SMS_PROVIDER=brevo --app suoops-backend
```

Verify configuration:
```bash
heroku config --app suoops-backend | grep BREVO
```

## Step 5: Test SMS

### Using Brevo Dashboard:
1. Go to **SMS** → **Campaigns** → **Create an SMS campaign**
2. Test with your phone number
3. Verify you receive the message

### Using SuoOps:
1. Create an invoice with a customer phone number (with country code: +234...)
2. Check logs:
   ```bash
   heroku logs --tail --app suoops-backend | grep "SMS"
   ```
3. Customer should receive SMS with invoice details

## What Gets Sent?

### Invoice SMS (approx 150 chars):
```
New invoice from BusinessName: INV-123456
Amount: ₦50,000.00
Pay here: https://suoops.com/pay/INV-123456
```

### Receipt SMS (approx 120 chars):
```
Payment received! Thank you for paying invoice INV-123456
Amount: ₦50,000.00
Status: PAID
- BusinessName
```

## Multi-Channel Flow

When you create an invoice, SuoOps automatically sends:
1. 📧 **Email** (via Brevo SMTP) - Invoice PDF attached
2. 💬 **WhatsApp** (via Meta) - Message + PDF + Link
3. 📱 **SMS** (via Brevo API) - Short message + Link

All from the **same Brevo account**! 🎉

## Pricing Comparison

| Provider | Setup | Cost per SMS | Dashboard | Email Included |
|----------|-------|--------------|-----------|----------------|
| **Brevo** | ✅ Easy | ₦3-5 | ✅ Unified | ✅ Yes |
| Termii | Medium | ₦3-4 | Separate | ❌ No |
| Twilio | Complex | ₦5-7 | Separate | ❌ No |

## Benefits of Using Brevo

1. **Single Dashboard** - Email and SMS in one place
2. **Already Setup** - You're using it for email
3. **Unified Reporting** - See all communications
4. **Cost Effective** - Competitive pricing
5. **Easy Management** - One account, one API key

## Troubleshooting

### SMS not sending?
1. **Check API key**: Ensure `BREVO_API_KEY` is set
2. **Check credits**: Top up if balance is low
3. **Check phone format**: Must include country code with + (e.g., +2348012345678)
4. **Check logs**: `heroku logs --tail --app suoops-backend | grep SMS`

### SMS character limit exceeded?
- **160 characters = 1 SMS credit**
- Our messages are designed to fit within 160 chars
- Long messages automatically split (costs multiple credits)

### Sender name not appearing?
- Some networks may take time to show custom sender
- Default sender will be used if name not approved
- Check Brevo dashboard for sender approval status

## Support

### Brevo Support:
- Email: support@brevo.com
- Live Chat: Available in dashboard
- Documentation: https://developers.brevo.com/docs

### SuoOps Logs:
```bash
heroku logs --tail --app suoops-backend
```

## Cost Estimates (Brevo)

| Usage | SMS Count | Cost (₦) | Email | WhatsApp | Total Cost |
|-------|-----------|----------|-------|----------|------------|
| 100 invoices | 100 | ~400 | Free* | ~600 | ~1,000 |
| 500 invoices | 500 | ~2,000 | Free* | ~3,000 | ~5,000 |
| 1000 invoices | 1000 | ~4,000 | Free* | ~6,000 | ~10,000 |

*Email free up to 300/day on Brevo free plan

## Next Steps

1. ✅ Get Brevo SMS API key
2. ✅ Buy SMS credits (start with 500)
3. ✅ Set `BREVO_API_KEY` on Heroku
4. ✅ Test with a customer invoice
5. ✅ Monitor usage in Brevo dashboard

---

**Recommended**: Start with **500 SMS credits** (~₦2,000) to test the system, then scale up based on usage.

**Last Updated**: November 9, 2025
