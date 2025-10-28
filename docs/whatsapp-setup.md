# WhatsApp Business API Setup Guide

## Overview
This guide will help you configure the WhatsApp webhook for SuoPay to receive and process messages.

## Prerequisites
- WhatsApp Business Account
- Meta Business Manager access
- Phone Number ID and Business Account ID configured in Heroku

## Webhook Configuration

### 1. Webhook URL
Your WhatsApp webhook URL is:
```
https://api.suoops.com/webhooks/whatsapp
```

### 2. Configure in Meta Business Manager

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Navigate to your WhatsApp Business App
3. Go to **WhatsApp** → **Configuration**
4. Under **Webhook**, click **Edit**
5. Enter the webhook URL:
   ```
   https://api.suoops.com/webhooks/whatsapp
   ```
6. Enter a verification token (can be any string, e.g., `suoops_verify_2025`)
7. Click **Verify and Save**

### 3. Subscribe to Webhook Events

Subscribe to the following events:
- ✅ **messages** - To receive incoming messages

### 4. Test the Webhook

#### Manual Test
Send a test payload to verify the webhook is working:

```bash
curl -X POST https://api.suoops.com/webhooks/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "from": "+2347012345678",
    "text": "Invoice John Doe 50000 for consulting due tomorrow",
    "issuer_id": 1
  }'
```

Expected response:
```json
{
  "ok": true,
  "queued": true
}
```

#### WhatsApp Message Format

Users can send messages like:
- `Invoice John Doe 50000 for consulting due tomorrow`
- `Invoice Jane 25000 due next week`
- `Create invoice for Mike 100000`

The bot will:
1. Parse the message using NLP
2. Extract customer name, amount, and due date
3. Create an invoice
4. Send back the invoice ID and status

### 5. Environment Variables

Ensure these are set in Heroku:

```bash
# Check current values
heroku config --app suoops-backend

# Required variables
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_API_KEY=your_api_key
```

### 6. Webhook Verification

WhatsApp will send a GET request to verify your webhook. The endpoint needs to:
1. Parse the `hub.mode`, `hub.verify_token`, and `hub.challenge` parameters
2. Verify the token matches your configured token
3. Return the `hub.challenge` value

**Note**: Currently, the webhook only handles POST requests. We need to add GET handler for verification.

## Adding Verification Handler

Add this to `app/api/routes_webhooks.py`:

```python
@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Webhook verification endpoint for WhatsApp"""
    from app.core.config import settings
    
    # You'll need to add WHATSAPP_VERIFY_TOKEN to settings
    verify_token = settings.WHATSAPP_VERIFY_TOKEN or "suoops_verify_2025"
    
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return PlainTextResponse(hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")
```

## Message Processing Flow

1. **Webhook receives message** → Queued to Celery
2. **Celery worker processes** → NLP parses the message
3. **Invoice created** → Confirmation sent back to user
4. **PDF generated** → Can be sent as WhatsApp document (optional)

## Troubleshooting

### Webhook not receiving messages
- Verify the webhook URL is correct in Meta Business Manager
- Check that the webhook is subscribed to `messages` events
- Check Heroku logs: `heroku logs --tail --app suoops-backend`

### Messages not being processed
- Check Celery worker is running: `heroku ps --app suoops-backend`
- Verify Redis is connected: `heroku redis:info --app suoops-backend`
- Check worker logs for errors

### Cannot verify webhook
- Ensure GET endpoint is implemented
- Verify token matches the one in Meta Business Manager
- Check response is plain text, not JSON

## Next Steps

1. Implement the GET verification endpoint
2. Test with a real WhatsApp message
3. Enhance NLP parsing for better accuracy
4. Add support for sending PDF invoices via WhatsApp
5. Add support for payment status updates via WhatsApp
