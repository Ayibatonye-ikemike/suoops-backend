# DNS Configuration for suoops.com

## ✅ Completed Updates

### Render Backend
- **App renamed**: `suopay-backend` → `suoops-backend`
- **New URL**: `https://api.suoops.com`
- **Custom domain**: `api.suoops.com`
- **DNS Target**: `api.suoops.com`

### Vercel Frontend
- **Project renamed**: `suopay-frontend` → `suoops-frontend`
- **Custom domain**: `suoops.com`
- **Deployment URL**: `https://suoops-frontend-kle9q08n1-ikemike.vercel.app`
- **Nameservers**: Vercel DNS (`ns1.vercel-dns.com`, `ns2.vercel-dns.com`)

---

## 🔧 Required DNS Configuration in Namecheap

You need to configure DNS records for `suoops.com` in your Namecheap account:

### Option 1: Using Vercel Nameservers (Recommended - Easiest)

1. **Go to Namecheap Dashboard** → Domain List → `suoops.com` → Manage
2. **Click on "Nameservers"** section
3. **Select "Custom DNS"**
4. **Enter Vercel nameservers**:
   ```
   ns1.vercel-dns.com
   ns2.vercel-dns.com
   ```
5. **Save changes**
6. **Wait 5-10 minutes** for propagation

**With this option, Vercel manages ALL DNS records automatically including the API subdomain.**

---

### Option 2: Using Namecheap DNS (More Control)

If you want to keep using Namecheap's nameservers:

1. **Go to Namecheap Dashboard** → Domain List → `suoops.com` → Advanced DNS
2. **Delete all existing A/CNAME records** for root domain and API subdomain
3. **Add these records**:

#### Frontend (suoops.com):
```
Type: CNAME
Host: @
Value: cname.vercel-dns.com
TTL: Automatic
```

```
Type: CNAME
Host: www
Value: cname.vercel-dns.com
TTL: Automatic
```

#### Backend API (api.suoops.com):
```
Type: CNAME
Host: api
Value: api.suoops.com
TTL: Automatic
```

4. **Save all records**
5. **Wait 10-30 minutes** for DNS propagation

---

## 🔍 Verify DNS Configuration

After configuring DNS, wait a few minutes then verify:

### Check Frontend DNS:
```bash
# Should show Vercel IPs
dig suoops.com
dig www.suoops.com

# Or use online tool
https://dnschecker.org/#A/suoops.com
```

### Check Backend API DNS:
```bash
# Should show Renderdns.com CNAME
dig api.suoops.com

# Or use online tool
https://dnschecker.org/#CNAME/api.suoops.com
```

### Test Endpoints:
```bash
# Frontend (should load the website)
curl -I https://suoops.com

# Backend API (should return API response)
curl -I https://api.suoops.com/health
```

---

## 📊 Current Status

### ✅ Completed:
- [x] Render app renamed to `suoops-backend`
- [x] Vercel project renamed to `suoops-frontend`
- [x] Custom domain added to Render: `api.suoops.com`
- [x] Custom domain added to Vercel: `suoops.com`
- [x] Removed old `api.suopay.io` from Render
- [x] Removed old `suopay.io` from Vercel
- [x] Cleaned up old Vercel deployment aliases

### ⚠️ Pending (Requires Your Action):
- [ ] **Configure DNS in Namecheap** (see instructions above)
- [ ] Wait for DNS propagation (5-30 minutes)
- [ ] Verify SSL certificates are issued (Render ACM will auto-retry)
- [ ] Test both `https://suoops.com` and `https://api.suoops.com`

---

## 🚨 Current Issues

### Render SSL Certificate Failing
```
api.suoops.com - Status: Failing
Reason: CDN not returning HTTP challenge
```

**Why?** Render can't verify the domain because DNS is not pointing to Render yet.

**Solution:** Once you configure DNS in Namecheap (see above), Render will automatically retry verification every few minutes and issue the SSL certificate.

---

## 📝 What Changed

### Before:
- Render app: `suopay-backend`
- Render domain: `api.suopay.io`
- Vercel project: `suopay-frontend`
- Vercel domain: `suopay.io`

### After:
- Render app: `suoops-backend`
- Render domain: `api.suoops.com`
- Vercel project: `suoops-frontend`
- Vercel domain: `suoops.com`

---

## 🆘 Troubleshooting

### If SSL still failing after 1 hour:
```bash
# Force refresh ACM status
# (TLS managed automatically by Render) -a suoops-backend

# Check status
# (TLS managed automatically by Render) -a suoops-backend
```

### If Vercel domain not working:
1. Check nameservers are correct in Namecheap
2. Wait longer (DNS can take up to 48 hours in rare cases)
3. Try clearing browser cache
4. Try incognito/private browsing mode

### If API calls failing:
1. Verify DNS is pointing correctly: `dig api.suoops.com`
2. Check Render app is running: `# Check service status in Render Dashboard`
3. Check logs: `# Stream logs from Render Dashboard`

---

## 📞 Next Steps

1. **Go to Namecheap now** and configure DNS (Option 1 is easiest)
2. **Wait 10-15 minutes** for DNS propagation
3. **Check Render dashboard** - SSL should change from "Failing" to "OK"
4. **Test your site**: Visit `https://suoops.com` and `https://api.suoops.com/health`
5. **Update documentation** once everything is working

---

**Note**: After DNS is configured and SSL certificates are issued, both sites will be fully operational with HTTPS!
