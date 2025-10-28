# DNS Records for Amazon SES - suoops.com

## 📋 Complete List of DNS Records to Add

You need to add **6 DNS records** total to your domain registrar (Namecheap, GoDaddy, Cloudflare, etc.)

---

## 🔐 DKIM Records (3 CNAME Records)

These authenticate your emails and prove you own the domain.

### Record 1:
```
Type: CNAME
Name: iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suoops.com
Value: iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com
TTL: Automatic (or 3600)
```

### Record 2:
```
Type: CNAME
Name: flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey.suoops.com
Value: flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com
TTL: Automatic (or 3600)
```

### Record 3:
```
Type: CNAME
Name: 6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey.suoops.com
Value: 6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com
TTL: Automatic (or 3600)
```

---

## 📧 MAIL FROM Records (2 Records)

These handle email bounces and improve deliverability.

### Record 4 (MX Record):
```
Type: MX
Name: mail.suoops.com
Value: 10 feedback-smtp.eu-north-1.amazonses.com
Priority: 10
TTL: Automatic (or 3600)
```

### Record 5 (TXT Record - SPF):
```
Type: TXT
Name: mail.suoops.com
Value: "v=spf1 include:amazonses.com ~all"
TTL: Automatic (or 3600)
```

**Note:** Keep the quotes in the value!

---

## 🛡️ DMARC Record (1 TXT Record)

This tells email servers how to handle authentication failures.

### Record 6:
```
Type: TXT
Name: _dmarc.suoops.com
Value: "v=DMARC1; p=none;"
TTL: Automatic (or 3600)
```

**Note:** Keep the quotes in the value!

---

## 📝 How to Add Records (by Provider)

### For Namecheap:

1. **Login to Namecheap:** https://www.namecheap.com/myaccount/login/
2. **Domain List** → Click **Manage** next to `suoops.com`
3. **Advanced DNS** tab
4. Click **Add New Record**

**For CNAME Records:**
- Type: `CNAME Record`
- Host: `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey` (remove `.suoops.com`)
- Value: `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`
- TTL: `Automatic`

**For MX Record:**
- Type: `MX Record`
- Host: `mail` (remove `.suoops.com`)
- Value: `feedback-smtp.eu-north-1.amazonses.com`
- Priority: `10`
- TTL: `Automatic`

**For TXT Records:**
- Type: `TXT Record`
- Host: `mail` or `_dmarc` (remove `.suoops.com`)
- Value: `"v=spf1 include:amazonses.com ~all"` (keep quotes!)
- TTL: `Automatic`

---

### For GoDaddy:

1. **Login to GoDaddy:** https://account.godaddy.com/
2. **My Products** → **DNS** next to `suoops.com`
3. Click **Add** button

**For CNAME Records:**
- Type: `CNAME`
- Name: `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey`
- Value: `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`
- TTL: `1 Hour`

**For MX Record:**
- Type: `MX`
- Name: `mail`
- Value: `feedback-smtp.eu-north-1.amazonses.com`
- Priority: `10`
- TTL: `1 Hour`

**For TXT Records:**
- Type: `TXT`
- Name: `mail` or `_dmarc`
- Value: `v=spf1 include:amazonses.com ~all` (GoDaddy adds quotes automatically)
- TTL: `1 Hour`

---

### For Cloudflare:

1. **Login to Cloudflare:** https://dash.cloudflare.com/
2. Select `suoops.com` domain
3. **DNS** tab → **Add record**

**For CNAME Records:**
- Type: `CNAME`
- Name: `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey`
- Target: `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`
- Proxy status: `DNS only` (gray cloud)
- TTL: `Auto`

**For MX Record:**
- Type: `MX`
- Name: `mail`
- Mail server: `feedback-smtp.eu-north-1.amazonses.com`
- Priority: `10`
- TTL: `Auto`

**For TXT Records:**
- Type: `TXT`
- Name: `mail` or `_dmarc`
- Content: `v=spf1 include:amazonses.com ~all` (no quotes needed)
- TTL: `Auto`

---

## ⚠️ Important Notes

### 1. **Remove Domain Suffix**
When adding records, most DNS providers require you to **remove the domain suffix**:

❌ **Wrong:** `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suoops.com`
✅ **Correct:** `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey`

Or:

❌ **Wrong:** `mail.suoops.com`
✅ **Correct:** `mail`

**Exception:** Some providers want the full name including `.suoops.com` - check their interface!

### 2. **Keep Quotes for TXT Records**
- SPF: `"v=spf1 include:amazonses.com ~all"`
- DMARC: `"v=DMARC1; p=none;"`

Some providers add quotes automatically, some require them manually.

### 3. **MX Record Value Format**
Some providers want:
- ✅ `10 feedback-smtp.eu-north-1.amazonses.com` (priority + space + value)
- ✅ Or separate fields: Priority: `10`, Value: `feedback-smtp.eu-north-1.amazonses.com`

Check your provider's format!

---

## ✅ Quick Checklist

Add these 6 records:

- [ ] **CNAME 1:** `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey` → `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`
- [ ] **CNAME 2:** `flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey` → `flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com`
- [ ] **CNAME 3:** `6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey` → `6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com`
- [ ] **MX:** `mail` → `10 feedback-smtp.eu-north-1.amazonses.com`
- [ ] **TXT 1:** `mail` → `"v=spf1 include:amazonses.com ~all"`
- [ ] **TXT 2:** `_dmarc` → `"v=DMARC1; p=none;"`

---

## 🕐 DNS Propagation Time

After adding all records:
- **Minimum:** 15 minutes
- **Average:** 1-2 hours
- **Maximum:** 48 hours

---

## 🔍 Verify DNS Records (After Adding)

### Check if records are live:

```bash
# Check DKIM records
dig iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suoops.com CNAME
dig flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey.suoops.com CNAME
dig 6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey.suoops.com CNAME

# Check MX record
dig mail.suoops.com MX

# Check TXT records
dig mail.suoops.com TXT
dig _dmarc.suoops.com TXT
```

**Expected output:**
- CNAME records should show `.dkim.amazonses.com` in the answer
- MX record should show `feedback-smtp.eu-north-1.amazonses.com`
- TXT records should show the SPF and DMARC values

### Or use online tools:
- **MXToolbox:** https://mxtoolbox.com/SuperTool.aspx
- **DNS Checker:** https://dnschecker.org/
- **What's My DNS:** https://www.whatsmydns.net/

---

## 🚦 Check Verification Status in AWS

1. Go to AWS SES Console: https://console.aws.amazon.com/ses/
2. Click **Identities** (left sidebar)
3. Click **suoops.com**
4. Check **Status:**
   - 🟡 **Pending verification** - DNS not propagated yet (wait)
   - 🟢 **Verified** - All good! Ready to send emails

**DKIM Status:**
- 🟡 **Pending** - Wait for DNS propagation
- 🟢 **Successful** - DKIM authenticated

**Custom MAIL FROM Status:**
- 🟡 **Pending** - Wait for DNS propagation
- 🟢 **Successful** - MX and TXT records verified

---

## 🐛 Troubleshooting

### Issue: Records not verifying after 24 hours

**Check:**
1. Did you remove `.suoops.com` from the Name field?
2. Are quotes included in TXT record values?
3. Is the MX priority set to `10`?
4. Run `dig` commands to verify records are live

**Fix:**
```bash
# Check if DNS is propagated
dig iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suoops.com CNAME

# Should show:
# iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suoops.com. 3600 IN CNAME iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com.
```

### Issue: MX record not accepting value format

**Try these formats:**
- Format 1: Value: `10 feedback-smtp.eu-north-1.amazonses.com`
- Format 2: Priority: `10`, Value: `feedback-smtp.eu-north-1.amazonses.com`
- Format 3: Value: `feedback-smtp.eu-north-1.amazonses.com`, Priority: `10`

### Issue: TXT record value too long

**Solution:**
Break into multiple strings (some providers):
```
"v=spf1 " "include:amazonses.com " "~all"
```

---

## 📞 DNS Provider Support

If you need help adding records:

- **Namecheap Support:** https://www.namecheap.com/support/
- **GoDaddy Support:** https://www.godaddy.com/help
- **Cloudflare Support:** https://support.cloudflare.com/

Tell them: "I need to add DNS records for Amazon SES email authentication"

---

## 🎯 Next Steps

1. ✅ Add all 6 DNS records to your domain registrar
2. ⏰ Wait 15 minutes - 48 hours for DNS propagation
3. 🔍 Check verification status in AWS SES Console
4. ✅ Once verified, create SMTP credentials
5. 🚀 Configure Heroku with SES credentials
6. 📧 Test email sending!

---

## 📚 What Each Record Does

| Record Type | Purpose |
|-------------|---------|
| **DKIM (3 CNAME)** | Proves emails weren't tampered with in transit |
| **MX** | Tells where bounced emails should go (AWS handles) |
| **SPF (TXT)** | Lists authorized servers for sending email |
| **DMARC (TXT)** | Instructs servers how to handle failed authentication |

---

**Which DNS provider are you using?** (Namecheap, GoDaddy, Cloudflare, etc.)

I can give you **exact step-by-step instructions** for your specific provider!

Last updated: October 22, 2025
