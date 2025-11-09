# Termii Setup Guide for SuoOps

## Overview
Termii is a Nigerian communication platform that provides SMS and WhatsApp messaging services. This guide will help you set up Termii for multi-channel notifications in SuoOps.

## Prerequisites
1. Termii account (sign up at https://termii.com)
2. Business verification documents
3. Heroku CLI access to set environment variables

## Step 1: Create Termii Account
1. Go to https://termii.com
2. Click "Sign Up" and create your account
3. Verify your email address
4. Complete your business profile

## Step 2: Get Your API Key
1. Log in to your Termii dashboard
2. Navigate to **Settings** → **API Keys**
3. Copy your **Live API Key** (starts with `TL...`)
4. Keep this key secure - you'll add it to Heroku

## Step 3: Request Sender ID for SMS

### What is a Sender ID?
A Sender ID is the name that appears as the sender when customers receive your SMS messages.

### Requirements:
- **Maximum 11 characters**
- Recommended: `SuoOps` (7 characters)
- Must be alphanumeric (no special characters)

### How to Request:
1. In Termii dashboard, go to **Settings** → **Sender ID**
2. Click "Request Sender ID"
3. Fill in the form:
   - **Sender ID**: `SuoOps`
   - **Company**: SuoOps
   - **Use Case**: "Invoice notifications and payment receipts for businesses. Example: 'New invoice from BusinessName: INV-123 Amount: ₦50,000.00 Pay here: https://suoops.com/pay/INV-123'"

### Approval Time:
- **24-48 hours** on weekdays
- Only processed Monday to Friday
- You'll receive an email when approved

### Testing Before Approval:
While waiting for approval, you can test with Termii's default Sender ID, but it won't show your brand name.

## Step 4: Request Device ID for WhatsApp (Optional)

### What is a Device ID?
A Device ID allows you to send WhatsApp messages through Termii's WhatsApp API.

### Requirements:
- **Maximum 9 characters**
- Only for: logistics, financial, health, and agric-tech companies
- SuoOps qualifies as **financial technology** (invoicing/payment platform)

### How to Request:
1. In Termii dashboard, go to **WhatsApp** → **Request Device ID**
2. Fill in the form:
   - **Device ID**: `SuoOps` (7 characters)
   - **Company**: SuoOps
   - **Industry**: Financial Technology
   - **Use Case**: "Invoice notifications and payment receipts for SMEs"

### Testing Without Approved Device ID:
- Use the default test ID: `TID`
- Only works with **test API keys**
- For production, you MUST have an approved Device ID

### Note:
**For now, we recommend using Meta's WhatsApp Business API** (already configured in SuoOps) instead of Termii's WhatsApp, as it's more reliable and feature-rich. Use Termii only for SMS.

## Step 5: Configure Heroku Environment Variables

Once you have your API key and Sender ID approved, add them to Heroku:

```bash
# Required: Termii API Key
heroku config:set TERMII_API_KEY=TLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx --app suoops-backend

# Required: Your approved Sender ID (or use default during testing)
heroku config:set TERMII_SENDER_ID=SuoOps --app suoops-backend

# Optional: Device ID for WhatsApp via Termii (use TID for testing)
heroku config:set TERMII_DEVICE_ID=TID --app suoops-backend

# Confirm SMS provider is set to Termii
heroku config:set SMS_PROVIDER=termii --app suoops-backend
```

Verify the configuration:
```bash
heroku config --app suoops-backend | grep TERMII
```

## Step 6: Test SMS Notifications

### Using Termii Dashboard:
1. Go to **Messaging** → **Send SMS**
2. Test with your phone number
3. Verify you receive the message with your Sender ID

### Using SuoOps:
1. Create an invoice with a customer phone number
2. Check logs to confirm SMS was sent:
   ```bash
   heroku logs --tail --app suoops-backend | grep "SMS"
   ```
3. Customer should receive:
   - SMS with invoice details and payment link
   - WhatsApp message with PDF (if WhatsApp is configured)
   - Email with PDF (if email is provided)

## Pricing (Termii Nigeria)

### SMS Pricing:
- **₦2.50 - ₦4.00 per SMS** (depending on volume)
- Cost varies by network (MTN, Glo, Airtel, 9mobile)
- Bulk discounts available

### WhatsApp Pricing:
- **₦5.00 - ₦8.00 per message**
- Check latest rates in your Termii dashboard

### Recommendations:
1. **Start with ₦5,000 - ₦10,000** in your Termii wallet
2. Monitor usage in dashboard
3. Set up **auto-recharge** to avoid service interruption

## Troubleshooting

### SMS not sending?
1. **Check API key**: Ensure `TERMII_API_KEY` is set correctly
2. **Check wallet balance**: Top up if low
3. **Check Sender ID approval**: Must be approved for production
4. **Check phone format**: Must include country code (e.g., `2348012345678`)

### Sender ID not appearing?
1. **Approval pending**: Wait 24-48 hours on weekdays
2. **Using test keys**: Default sender will be used
3. **Telco issues**: Some networks take longer to update

### SMS character limit exceeded?
- **160 characters = 1 SMS unit**
- Our invoice SMS is designed to fit within 160 characters
- Check logs for truncation

## Support

### Termii Support:
- Email: support@termii.com
- Phone: +234 906 000 0121
- Live Chat: Available in dashboard

### SuoOps Configuration Help:
Check our logs for detailed error messages:
```bash
heroku logs --tail --app suoops-backend
```

## Best Practices

1. **Monitor costs**: SMS can add up - track usage in Termii dashboard
2. **Test thoroughly**: Use test API keys before going live
3. **Keep wallet funded**: Set up auto-recharge alerts
4. **Sender ID branding**: Use your approved Sender ID for better trust
5. **Combine channels**: Use SMS as backup when WhatsApp/Email fails

## Next Steps

After Termii is configured:
1. ✅ SMS will automatically send when invoices are created
2. ✅ SMS receipts will send when payments are confirmed  
3. ✅ Works alongside Email and WhatsApp notifications
4. ✅ Customers get multiple channels to receive invoices

---

**Last Updated**: November 9, 2025
