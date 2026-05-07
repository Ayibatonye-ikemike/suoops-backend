# Custom Domain Migration - Completed ✅

**Migration Date:** October 22, 2025  
**Status:** Successfully migrated from Render domain to custom domain

---

## Summary

The Suopay API has been successfully migrated from the Render-provided domain to a custom domain with SSL certificate.

### URLs Changed

| Service | Old URL | New URL | Status |
|---------|---------|---------|--------|
| **API Base** | `https://api.suoops.com` | `https://api.suoops.com` | ✅ Active |
| **Health Check** | `https://api.suoops.com/healthz` | `https://api.suoops.com/healthz` | ✅ Active |
| **Webhooks (Paystack)** | `https://api.suoops.com/webhooks/paystack` | `https://api.suoops.com/webhooks/paystack` | ✅ Active |
| **Webhooks (WhatsApp)** | `https://api.suoops.com/webhooks/whatsapp` | `https://api.suoops.com/webhooks/whatsapp` | ✅ Active |

---

## Technical Details

### DNS Configuration

**Nameservers:** Vercel DNS
- `ns1.vercel-dns.com`
- `ns2.vercel-dns.com`

**DNS Records:**
```
api.suoops.com.  60  IN  CNAME  api.suoops.com.
```

**Resolution:**
```bash
$ dig api.suoops.com +short
api.suoops.com.
35.71.179.82
99.83.220.108
75.2.60.68
13.248.244.96
```

### SSL Certificate

**Provider:** Let's Encrypt (via Render ACM)  
**Issuer:** R12/Let's Encrypt  
**Valid From:** October 19, 2025  
**Expires:** January 17, 2026  
**Renewal:** Scheduled for December 17, 2025  
**Status:** ✅ Verified by root authority

```bash
$ # (TLS managed automatically by Render) -a suoops-backend
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
api.suoops.com   canonical name = api.suoops.com.
Name:   api.suoops.com
Address: 13.248.244.96
Name:   api.suoops.com
Address: 75.2.60.68
Name:   api.suoops.com
Address: 35.71.179.82
Name:   api.suoops.com
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
  - Render will auto-renew on Dec 17, 2025
  - Check status: `# (TLS managed automatically by Render) -a suoops-backend`

- [ ] Update any external integrations
  - Check if any third-party services reference the old URL
  - Update API documentation in external platforms

### Optional
- [ ] Set up domain redirect (Render → Custom)
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
   Should return Render IPs (35.71.179.82, etc.)

2. **Check SSL Certificate**
   ```bash
   # (TLS managed automatically by Render) -a suoops-backend
   ```
   Should show valid certificate

3. **Check Render Domain**
   ```bash
   Render domains -a suoops-backend
   ```
   Should list `api.suoops.com` with CNAME target

4. **Fallback to Render URL**
   If custom domain fails, the old Render URL still works:
   ```
   https://api.suoops.com
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

**Deployment Platform:** Render  
**DNS Provider:** Vercel  
**SSL Provider:** Let's Encrypt (via Render ACM)  

**Commands for Monitoring:**
```bash
# Check app status
# Check service status in Render Dashboard

# Check SSL certificate
# (TLS managed automatically by Render) -a suoops-backend

# Check DNS configuration
Render domains -a suoops-backend

# View logs
# Stream logs from Render Dashboard
```

---

**Migration completed successfully! 🎉**

The API is now accessible at `https://api.suoops.com` with full SSL/TLS encryption.
