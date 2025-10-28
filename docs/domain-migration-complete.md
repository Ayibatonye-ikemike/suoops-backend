# Custom Domain Migration - Completed ✅

**Migration Date:** October 22, 2025  
**Status:** Successfully migrated from Heroku domain to custom domain

---

## Summary

The Suopay API has been successfully migrated from the Heroku-provided domain to a custom domain with SSL certificate.

### URLs Changed

| Service | Old URL | New URL | Status |
|---------|---------|---------|--------|
| **API Base** | `https://suoops-backend.herokuapp.com` | `https://api.suoops.com` | ✅ Active |
| **Health Check** | `https://suoops-backend.herokuapp.com/healthz` | `https://api.suoops.com/healthz` | ✅ Active |
| **Webhooks (Paystack)** | `https://suoops-backend.herokuapp.com/webhooks/paystack` | `https://api.suoops.com/webhooks/paystack` | ✅ Active |
| **Webhooks (WhatsApp)** | `https://suoops-backend.herokuapp.com/webhooks/whatsapp` | `https://api.suoops.com/webhooks/whatsapp` | ✅ Active |

---

## Technical Details

### DNS Configuration

**Nameservers:** Vercel DNS
- `ns1.vercel-dns.com`
- `ns2.vercel-dns.com`

**DNS Records:**
```
api.suoops.com.  60  IN  CNAME  integrative-perch-ft4hedhc20lv0v5qv77f4a15.herokudns.com.
```

**Resolution:**
```bash
$ dig api.suoops.com +short
integrative-perch-ft4hedhc20lv0v5qv77f4a15.herokudns.com.
35.71.179.82
99.83.220.108
75.2.60.68
13.248.244.96
```

### SSL Certificate

**Provider:** Let's Encrypt (via Heroku ACM)  
**Issuer:** R12/Let's Encrypt  
**Valid From:** October 19, 2025  
**Expires:** January 17, 2026  
**Renewal:** Scheduled for December 17, 2025  
**Status:** ✅ Verified by root authority

```bash
$ heroku certs:auto -a suoops-backend
=== Automatic Certificate Management is enabled on suoops-backend

Certificate details:
Common Name(s): api.suoops.com
Expires At:     2026-01-17 11:58 UTC
Issuer:         /CN=R12/O=Let's Encrypt/C=US
Subject:        /CN=api.suoops.com
SSL certificate is verified by a root authority.
```

---

## Configuration Changes

### Frontend Configuration

**File:** `frontend/vercel.json`

```json
{
  "env": {
    "NEXT_PUBLIC_API_BASE_URL": "https://api.suoops.com"
  }
}
```

**File:** `frontend/src/lib/config.ts`

```typescript
const defaultConfig = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  // ...
};
```

### Documentation Updated

All documentation files have been updated to reference the new domain:

- ✅ `docs/webhook-setup.md` - Webhook URLs updated
- ✅ `docs/testing-summary.md` - Test commands updated
- ✅ `docs/payment-testing-guide.md` - API endpoints updated
- ✅ `docs/customer-invoice-flow.md` - Environment variables updated
- ✅ `DEPLOYMENT_STATUS.md` - Health check URL updated

---

## Verification Tests

### 1. DNS Resolution

```bash
$ nslookup api.suoops.com 8.8.8.8
Server:         8.8.8.8
Address:        8.8.8.8#53

Non-authoritative answer:
api.suoops.com   canonical name = integrative-perch-ft4hedhc20lv0v5qv77f4a15.herokudns.com.
Name:   integrative-perch-ft4hedhc20lv0v5qv77f4a15.herokudns.com
Address: 13.248.244.96
Name:   integrative-perch-ft4hedhc20lv0v5qv77f4a15.herokudns.com
Address: 75.2.60.68
Name:   integrative-perch-ft4hedhc20lv0v5qv77f4a15.herokudns.com
Address: 35.71.179.82
Name:   integrative-perch-ft4hedhc20lv0v5qv77f4a15.herokudns.com
Address: 99.83.220.108
```

### 2. SSL/TLS Test

```bash
$ curl -I https://api.suoops.com/healthz
HTTP/2 200
content-type: application/json
# ... SSL handshake successful
```

### 3. API Health Check

```bash
$ curl https://api.suoops.com/healthz
{"status":"ok"}
```

### 4. Full API Test

```bash
# Login
$ curl -X POST https://api.suoops.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone": "+2347012345678", "password": "TestPassword123"}'

# Create Invoice
$ curl -X POST https://api.suoops.com/invoices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "customer_name":"Test Customer",
    "customer_phone":"+2348012345678",
    "amount":50000,
    "lines":[{"description":"Test Service","quantity":1,"unit_price":50000}]
  }'
```

---

## Migration Timeline

| Date | Action | Status |
|------|--------|--------|
| Oct 19, 2025 | SSL certificate issued | ✅ Complete |
| Oct 22, 2025 | DNS CNAME record added in Vercel | ✅ Complete |
| Oct 22, 2025 | DNS propagation verified | ✅ Complete |
| Oct 22, 2025 | Frontend configuration updated | ✅ Complete |
| Oct 22, 2025 | Documentation updated | ✅ Complete |
| Oct 22, 2025 | Migration verified and tested | ✅ Complete |

---

## Next Steps

### Immediate (Already Done)
- ✅ Update frontend to use new domain
- ✅ Update all documentation
- ✅ Verify SSL certificate
- ✅ Test all endpoints

### Recommended (To Do)
- [ ] Update Paystack webhook URL in dashboard
  - Login to https://dashboard.paystack.com/#/settings/webhooks
  - Update webhook URL to: `https://api.suoops.com/webhooks/paystack`

- [ ] Update WhatsApp webhook URL in Meta Business Suite
  - Update webhook URL to: `https://api.suoops.com/webhooks/whatsapp`

- [ ] Monitor SSL certificate renewal
  - Heroku will auto-renew on Dec 17, 2025
  - Check status: `heroku certs:auto -a suoops-backend`

- [ ] Update any external integrations
  - Check if any third-party services reference the old URL
  - Update API documentation in external platforms

### Optional
- [ ] Set up domain redirect (Heroku → Custom)
  - Currently both URLs work
  - Could redirect old URL to new for SEO/consistency

- [ ] Add monitoring for custom domain
  - Set up uptime monitoring for `api.suoops.com`
  - Alert if DNS or SSL issues occur

---

## Troubleshooting

### If Custom Domain Stops Working

1. **Check DNS Resolution**
   ```bash
   dig api.suoops.com @8.8.8.8
   ```
   Should return Heroku IPs (35.71.179.82, etc.)

2. **Check SSL Certificate**
   ```bash
   heroku certs:auto -a suoops-backend
   ```
   Should show valid certificate

3. **Check Heroku Domain**
   ```bash
   heroku domains -a suoops-backend
   ```
   Should list `api.suoops.com` with CNAME target

4. **Fallback to Heroku URL**
   If custom domain fails, the old Heroku URL still works:
   ```
   https://suoops-backend.herokuapp.com
   ```

### DNS Cache Issues

If you see old DNS records locally:

```bash
# macOS
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

# Linux
sudo systemd-resolve --flush-caches

# Windows
ipconfig /flushdns
```

---

## Contact & Support

**Deployment Platform:** Heroku  
**DNS Provider:** Vercel  
**SSL Provider:** Let's Encrypt (via Heroku ACM)  

**Commands for Monitoring:**
```bash
# Check app status
heroku ps -a suoops-backend

# Check SSL certificate
heroku certs:auto -a suoops-backend

# Check DNS configuration
heroku domains -a suoops-backend

# View logs
heroku logs --tail -a suoops-backend
```

---

**Migration completed successfully! 🎉**

The API is now accessible at `https://api.suoops.com` with full SSL/TLS encryption.
