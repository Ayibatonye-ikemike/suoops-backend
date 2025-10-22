# WhatsApp Meta Business Manager Quick Setup

## ✅ Backend Configuration Complete

Your WhatsApp webhook is ready and running at:
```
https://api.suopay.io/webhooks/whatsapp
```

## Steps to Complete in Meta Business Manager

### 1. Access Your WhatsApp App
1. Go to https://developers.facebook.com/
2. Select your WhatsApp Business App
3. Navigate to **WhatsApp** → **Configuration**

### 2. Configure Webhook

#### Webhook URL
```
https://api.suopay.io/webhooks/whatsapp
```

#### Verify Token
```
suopay_verify_2025
```

#### Callback URL (if requested separately)
```
https://api.suopay.io/webhooks/whatsapp
```

### 3. Subscribe to Webhook Fields

Make sure to subscribe to:
- ✅ **messages** - Required for receiving user messages

### 4. Test the Integration

Send a test message to your WhatsApp Business number:
```
Invoice John Doe 50000 for consulting due tomorrow
```

Expected behavior:
- Message received by webhook
- Queued to Celery worker
- NLP parses the message
- Invoice created automatically
- Confirmation sent back to WhatsApp

### 5. Monitor Processing

Check logs to see message processing:
```bash
# Web dyno logs
heroku logs --tail --app suopay-backend --dyno web

# Worker dyno logs  
heroku logs --tail --app suopay-backend --dyno worker
```

## ✅ Current Status

- [x] Webhook endpoint deployed
- [x] GET verification handler working
- [x] POST message handler working
- [x] Celery worker running
- [x] Redis SSL issues fixed
- [x] Message queuing functional
- [ ] Meta Business Manager configuration (needs your action)

## Message Format Examples

Users can send messages like:
```
Invoice John Doe 50000 for consulting due tomorrow
Invoice Jane Smith 25000 due next week
Create invoice for Mike 100000
Invoice Sarah 75000 for design work
```

The NLP service will extract:
- Customer name
- Amount
- Due date (if specified)
- Service description (if included)

## Troubleshooting

### Webhook not receiving messages
1. Verify webhook URL in Meta: `https://api.suopay.io/webhooks/whatsapp`
2. Check verify token: `suopay_verify_2025`
3. Ensure subscribed to `messages` event

### Messages not processing
1. Check worker is running: `heroku ps --app suopay-backend`
2. View worker logs: `heroku logs --tail --app suopay-backend --dyno worker`
3. Verify Redis connection

### Need to restart worker
```bash
heroku ps:restart worker --app suopay-backend
```

## Environment Variables (Already Set)

```bash
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id  
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_VERIFY_TOKEN=suopay_verify_2025
```

## Next Steps

1. **Configure in Meta Business Manager** (5 minutes)
   - Add webhook URL
   - Enter verify token
   - Subscribe to messages event

2. **Test with Real WhatsApp Message**
   - Send test message to your business number
   - Verify invoice is created
   - Check confirmation is sent back

3. **Optional: Send PDF Invoices**
   - Enhance WhatsAppClient to send documents
   - Send generated PDF to customer via WhatsApp
   - Requires WhatsApp Cloud API document sending
