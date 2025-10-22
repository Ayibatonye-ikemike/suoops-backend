# Webhook Configuration Guide

## Paystack Webhook Setup

### Current Status
- ✅ Backend deployed and running
- ⏳ Custom domain SSL provisioning (api.suopay.io)
- ✅ Webhook endpoint ready

### Webhook URL

**Use this public-facing URL:**
```
https://api.suopay.io/webhooks/paystack
```

**Temporary URL (if custom domain not ready):**
```
**Webhook URL:**
```
https://api.suopay.io/webhooks/paystack
```
```

### Setup Steps in Paystack Dashboard

1. **Login to Paystack Dashboard**
   - Go to: https://dashboard.paystack.com/#/settings/webhooks

2. **Add Webhook URL**
   - Click "Add Webhook URL"
   - Enter: `https://api.suopay.io/webhooks/paystack`
   - Click "Save"

3. **Select Events to Listen For**
   - ✅ `charge.success` - Payment completed successfully
   - ✅ `charge.failed` - Payment failed
   - ✅ `transfer.success` - Payout completed
   - ✅ `transfer.failed` - Payout failed
   - ✅ `refund.processed` - Refund completed
   - ✅ `invoice.payment_failed` - Invoice payment failed
   - ✅ `invoice.update` - Invoice updated

4. **Copy the Webhook Secret**
   - After saving, Paystack will generate a webhook secret
   - Copy this secret (starts with `whsec_...` or similar)

5. **Add Secret to Heroku**
   ```bash
   heroku config:set PAYSTACK_WEBHOOK_SECRET=<your_webhook_secret> --app suopay-backend
   ```

6. **Update Local Environment**
   - Add to `.env` file:
   ```
   PAYSTACK_WEBHOOK_SECRET=<your_webhook_secret>
   ```

### Testing the Webhook

Once configured, you can test it from the Paystack dashboard:
1. Go to webhook settings
2. Click "Test webhook"
3. Select an event type
4. Click "Send test"

Check your application logs:
```bash
heroku logs --tail --app suopay-backend
```

### Webhook Verification

The webhook endpoint automatically verifies requests using:
- Paystack signature in the `x-paystack-signature` header
- Your `PAYSTACK_WEBHOOK_SECRET`

### Security

✅ **HTTPS only** - Webhooks only work over HTTPS
✅ **Signature verification** - All requests are verified
✅ **Secret rotation** - Update the secret if compromised

### Troubleshooting

**If webhook fails:**
1. Check Heroku logs: `heroku logs --tail --app suopay-backend`
2. Verify webhook secret is set: `heroku config:get PAYSTACK_WEBHOOK_SECRET --app suopay-backend`
3. Test endpoint manually: `curl -X POST https://api.suopay.io/webhooks/paystack`
4. Check Paystack webhook logs in dashboard

**Common Issues:**
- ❌ SSL certificate not ready → Use Heroku URL temporarily
- ❌ Wrong webhook secret → Update with correct secret
- ❌ Endpoint returns 401/403 → Check signature verification

### Monitoring

Check webhook delivery status in Paystack dashboard:
- Settings → Webhooks → View logs
- See successful/failed deliveries
- Retry failed webhooks manually

---

## WhatsApp Webhook Setup (Future)

When you're ready to set up WhatsApp webhooks:

**Webhook URL:**
```
https://api.suopay.io/webhooks/whatsapp
```

**Verification Token:** Will be configured in Meta Business Suite

---

## Other Payment Providers

### Flutterwave (When Ready)

**Webhook URL:**
```
https://api.suopay.io/webhooks/flutterwave
```

Follow similar steps in Flutterwave dashboard.

---

**Last Updated:** October 19, 2025
