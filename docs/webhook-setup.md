# Webhook Configuration Guide

## Paystack Webhook Setup (Subscription Payments)

### Current Status
- ✅ Backend deployed and running
- ✅ Webhook endpoint ready for subscription upgrades
   - Invoices are handled via manual bank transfer, so no invoice webhooks are required.

### Webhook URL

**Use this public-facing URL:**
```
https://api.suoops.com/webhooks/paystack
```

**Temporary URL (if custom domain not ready):**
```
**Webhook URL:**
```
https://api.suoops.com/webhooks/paystack
```
```

### Setup Steps in Paystack Dashboard

1. **Login to Paystack Dashboard**
   - Go to: https://dashboard.paystack.com/#/settings/webhooks

2. **Add Webhook URL**
   - Click "Add Webhook URL"
   - Enter: `https://api.suoops.com/webhooks/paystack`
   - Click "Save"

3. **Select Events to Listen For**
   - ✅ `charge.success` – Required to upgrade plans automatically after a successful subscription payment
   - (Optional) `charge.failed` – Useful if you want visibility into failed subscription attempts
   - No invoice-related events are needed because customer invoices are settled manually.

4. **No Extra Secret Needed**
   - Signature verification uses the same `PAYSTACK_SECRET` you already configured for initializing payments.
   - No additional Heroku config vars are required.

### Testing the Webhook

Once configured, you can test it from the Paystack dashboard:
1. Go to webhook settings
2. Click "Test webhook"
3. Select an event type
4. Click "Send test"

Check your application logs:
```bash
heroku logs --tail --app suoops-backend
```

### Webhook Verification

The webhook endpoint automatically verifies requests using the `x-paystack-signature` header hashed with `PAYSTACK_SECRET`.

### Security

✅ **HTTPS only** - Webhooks only work over HTTPS
✅ **Signature verification** - All requests are verified
✅ **Secret rotation** - Update the secret if compromised

### Troubleshooting

**If webhook fails:**
1. Check Heroku logs: `heroku logs --tail --app suoops-backend`
2. Verify webhook secret is set: `heroku config:get PAYSTACK_WEBHOOK_SECRET --app suoops-backend`
3. Test endpoint manually: `curl -X POST https://api.suoops.com/webhooks/paystack`
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
https://api.suoops.com/webhooks/whatsapp
```

**Verification Token:** Will be configured in Meta Business Suite

---

**Last Updated:** October 23, 2025
