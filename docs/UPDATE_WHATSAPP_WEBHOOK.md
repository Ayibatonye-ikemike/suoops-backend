# 🔄 Update WhatsApp Webhook Verify Token

**Date**: October 28, 2025  
**Status**: ⚠️ **ACTION REQUIRED**

---

## What Changed

Updated the WhatsApp webhook verify token as part of the suopay → suoops migration:

- **Old Token**: `suopay_verify_2025`
- **New Token**: `suoops_verify_2025`

---

## ✅ Already Updated

The following have been updated automatically:

1. **Backend Code** (`app/core/config.py`): ✅
2. **Backend Code** (`app/api/routes_webhooks.py`): ✅
3. **Heroku Config**: ✅ `heroku config:set WHATSAPP_VERIFY_TOKEN=suoops_verify_2025`
4. **All Documentation**: ✅
5. **Test Files**: ✅
6. **Scripts**: ✅

---

## ⚠️ ACTION REQUIRED: Update Meta Developer Console

You need to update the webhook configuration in Meta's Developer Console:

### Step 1: Go to Meta Developer Console

1. Visit: https://developers.facebook.com/apps
2. Select your WhatsApp Business app
3. Go to **WhatsApp** → **Configuration** (left sidebar)

### Step 2: Update Webhook

1. Find the **Webhooks** section
2. Click **Edit** next to the webhook URL
3. Update the **Verify Token** field:
   ```
   suoops_verify_2025
   ```
4. The **Callback URL** should still be:
   ```
   https://api.suoops.com/webhooks/whatsapp
   ```
5. Click **Verify and Save**

### Step 3: Verify the Webhook

Meta will send a verification request to your webhook. If successful, you'll see a green checkmark ✅

---

## 🧪 Test the Webhook

After updating in Meta Console, test the webhook:

### Test 1: Verify Endpoint (Manual)
```bash
curl -X GET "https://api.suoops.com/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=suoops_verify_2025&hub.challenge=test_123"
```

**Expected Response**: `test_123` (the challenge is echoed back)

### Test 2: Send a WhatsApp Message

1. Send a message to your WhatsApp Business number
2. Check Heroku logs:
   ```bash
   heroku logs --tail -a suoops-backend
   ```
3. You should see the message being processed

### Test 3: Run Automated Tests
```bash
cd /Users/ayibatonyeikemike/mywork/suopay.io
./scripts/test_whatsapp_webhook.sh
```

---

## 🚨 Troubleshooting

### If Webhook Verification Fails

**Error**: "The callback URL or verify token couldn't be validated"

**Solutions**:

1. **Double-check the token** in Meta Console matches exactly:
   ```
   suoops_verify_2025
   ```

2. **Check Heroku config**:
   ```bash
   heroku config:get WHATSAPP_VERIFY_TOKEN -a suoops-backend
   ```
   Should return: `suoops_verify_2025`

3. **Check the webhook endpoint** is accessible:
   ```bash
   curl -I https://api.suoops.com/webhooks/whatsapp
   ```
   Should return HTTP status code (even 405 is fine, means it's accessible)

4. **Restart the Heroku app**:
   ```bash
   heroku restart -a suoops-backend
   ```
   Then try verifying again in Meta Console

5. **Check Heroku logs** during verification:
   ```bash
   heroku logs --tail -a suoops-backend
   ```
   You should see the verification request

### If Messages Aren't Being Received

1. **Check webhook subscriptions** in Meta Console:
   - Go to **Webhooks** → **Webhook Fields**
   - Ensure `messages` is subscribed ✅

2. **Check Heroku logs**:
   ```bash
   heroku logs --tail -a suoops-backend | grep whatsapp
   ```

3. **Verify the phone number** is registered in Meta Console

---

## 📋 Complete Checklist

- [x] Update backend code (`app/core/config.py`)
- [x] Update backend code (`app/api/routes_webhooks.py`)
- [x] Update Heroku config variable
- [x] Update all documentation
- [x] Update test files
- [ ] **Update Meta Developer Console webhook** ⚠️ **DO THIS NOW**
- [ ] Test webhook verification
- [ ] Test sending a WhatsApp message
- [ ] Verify messages are being received and processed

---

## 🔗 Quick Links

- **Meta Developer Console**: https://developers.facebook.com/apps
- **Heroku Dashboard**: https://dashboard.heroku.com/apps/suoops-backend
- **API Webhook URL**: https://api.suoops.com/webhooks/whatsapp
- **Heroku Logs**: `heroku logs --tail -a suoops-backend`

---

## 📝 Notes

### Why Change the Token?

As part of the complete migration from `suopay` to `suoops`, we updated all references including the webhook verify token for consistency.

### Security Considerations

The verify token is used by Meta to confirm that webhook requests are coming from your server. It should be:
- ✅ Unique
- ✅ Secret (don't share publicly)
- ✅ Match between your code and Meta Console

The token `suoops_verify_2025` is secure enough for this purpose.

---

## ✅ Once Complete

After updating in Meta Console and verifying it works:

1. Send a test WhatsApp message
2. Verify it's processed correctly
3. Check that invoice creation still works via WhatsApp
4. Update this checklist as complete

**Status**: 🔴 **PENDING META CONSOLE UPDATE**

Once updated: Change status to 🟢 **COMPLETE**
