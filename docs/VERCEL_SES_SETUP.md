# Vercel DNS Setup for Amazon SES - Step by Step

## 🎯 Goal
Add 6 DNS records to your `suopay.io` domain in Vercel for Amazon SES email verification.

---

## 📝 Step-by-Step Instructions

### **Step 1: Login to Vercel**

1. Go to: https://vercel.com/login
2. Login with your account
3. You should see your dashboard

---

### **Step 2: Access Domain DNS Settings**

1. Click on your **profile/avatar** (bottom left)
2. Click **Domains** from the dropdown menu
3. Find **suopay.io** in the list
4. Click **suopay.io** to manage it
5. Scroll down to the **DNS Records** section

Or direct link: https://vercel.com/dashboard/domains/suopay.io

---

### **Step 3: Add DKIM Records (3 CNAME Records)**

Click **Add** button in the DNS Records section for each of these:

#### **DKIM Record 1:**
```
Type: CNAME
Name: iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey
Value: iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com
TTL: Auto (Vercel default)
```

**Exact Steps:**
1. Click **Add** button in DNS Records section
2. **Type:** Select `CNAME` from dropdown
3. **Name:** Enter `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey`
   - ⚠️ **Important:** Just the subdomain, without `.suopay.io`
4. **Value:** Enter `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`
5. Click **Save**

#### **DKIM Record 2:**
```
Type: CNAME
Name: flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey
Value: flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com
```

**Exact Steps:**
1. Click **Add** button
2. **Type:** `CNAME`
3. **Name:** `flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey`
4. **Value:** `flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com`
5. Click **Save**

#### **DKIM Record 3:**
```
Type: CNAME
Name: 6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey
Value: 6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com
```

**Exact Steps:**
1. Click **Add** button
2. **Type:** `CNAME`
3. **Name:** `6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey`
4. **Value:** `6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com`
5. Click **Save**

---

### **Step 4: Add MX Record (1 Record)**

```
Type: MX
Name: mail
Value: feedback-smtp.eu-north-1.amazonses.com
Priority: 10
```

**Exact Steps:**
1. Click **Add** button
2. **Type:** Select `MX` from dropdown
3. **Name:** Enter `mail`
4. **Value:** Enter `feedback-smtp.eu-north-1.amazonses.com`
5. **Priority:** Enter `10`
6. Click **Save**

---

### **Step 5: Add SPF Record (TXT Record for mail.suopay.io)**

```
Type: TXT
Name: mail
Value: v=spf1 include:amazonses.com ~all
```

**Exact Steps:**
1. Click **Add** button
2. **Type:** Select `TXT` from dropdown
3. **Name:** Enter `mail`
4. **Value:** Enter `v=spf1 include:amazonses.com ~all`
   - ⚠️ **No quotes needed** - Enter plain text
5. Click **Save**

---

### **Step 6: Add DMARC Record (TXT Record)**

```
Type: TXT
Name: _dmarc
Value: v=DMARC1; p=none;
```

**Exact Steps:**
1. Click **Add** button
2. **Type:** Select `TXT` from dropdown
3. **Name:** Enter `_dmarc`
4. **Value:** Enter `v=DMARC1; p=none;`
   - ⚠️ **No quotes needed** - Enter plain text
5. Click **Save**

---

## ✅ Verification Checklist

After adding all records, your DNS Records section should have:

- [x] **3 CNAME Records** with `._domainkey` in the Name
- [x] **1 MX Record** for `mail` subdomain
- [x] **2 TXT Records** (one for `mail`, one for `_dmarc`)

**Total: 6 new DNS records**

---

## 🕐 What Happens Next?

### **Immediate (Now):**
- You'll see all 6 records listed in Vercel's DNS Records section
- Each record shows the type, name, and value

### **5-30 minutes later (Vercel is FAST!):**
- DNS records propagate globally
- Vercel's DNS is very fast, usually 5-30 minutes
- Much faster than traditional DNS providers!

### **In AWS SES Console:**
1. Go to: https://console.aws.amazon.com/ses/
2. Click **Identities** → **suopay.io**
3. **Status** changes from "Pending verification" → "Verified" ✅
4. **DKIM status** changes from "Pending" → "Successful" ✅
5. **Custom MAIL FROM** changes from "Pending" → "Successful" ✅

---

## 🔍 Verify Your DNS Records

### **Option 1: Check in Vercel (Instant)**

In the DNS Records section, you should see all 6 records listed with their configurations.

### **Option 2: Check DNS Propagation (5-30 minutes)**

Run these commands in your terminal:

```bash
# Check DKIM Record 1
dig iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suopay.io CNAME

# Check DKIM Record 2
dig flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey.suopay.io CNAME

# Check DKIM Record 3
dig 6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey.suopay.io CNAME

# Check MX Record
dig mail.suopay.io MX

# Check SPF Record
dig mail.suopay.io TXT

# Check DMARC Record
dig _dmarc.suopay.io TXT
```

**Expected results:**
- CNAME records should show `.dkim.amazonses.com` in the answer
- MX record should show `feedback-smtp.eu-north-1.amazonses.com`
- TXT records should show `v=spf1` and `v=DMARC1`

### **Option 3: Use Online Tool**

1. Go to: https://mxtoolbox.com/SuperTool.aspx
2. Enter: `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suopay.io`
3. Select **CNAME Lookup**
4. Should show: `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`

Repeat for other records.

---

## ⚠️ Vercel-Specific Notes

### **1. Domain Suffix**
Vercel automatically appends `.suopay.io` to the Name field.

❌ **Don't enter:** `mail.suopay.io`
✅ **Do enter:** `mail`

### **2. No Quotes for TXT Records**
Vercel doesn't require quotes for TXT record values.

✅ **Enter:** `v=spf1 include:amazonses.com ~all`
❌ **Not:** `"v=spf1 include:amazonses.com ~all"`

### **3. Propagation Speed**
Vercel DNS is **much faster** than traditional providers:
- Traditional (Namecheap, GoDaddy): 1-48 hours
- **Vercel: 5-30 minutes** ⚡

### **4. Record Management**
- Each record can be edited or deleted individually
- Click the **⋮** (three dots) next to a record to edit/delete
- Changes take effect within minutes

### **5. Conflict with Existing Records**
If you already have records for `mail` subdomain or `_dmarc`:
1. Click **⋮** next to the existing record
2. Select **Delete**
3. Add the new AWS SES records

---

## 📸 What You Should See in Vercel

### **DNS Records Section:**

After adding all records, you should see something like:

```
DNS Records

Type    Name                                              Value                                                 
────────────────────────────────────────────────────────────────────────────────────────────────────────────
CNAME   iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey     iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com
CNAME   flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey     flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com
CNAME   6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey     6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com
MX      mail                                              feedback-smtp.eu-north-1.amazonses.com (Priority: 10)
TXT     mail                                              v=spf1 include:amazonses.com ~all
TXT     _dmarc                                            v=DMARC1; p=none;
```

**Note:** Your existing records (A, CNAME for deployment, etc.) will still be there - that's normal!

---

## 🚀 Vercel DNS Advantages

### **Why Vercel DNS is Great:**

✅ **Fast Propagation:** 5-30 minutes vs 1-48 hours elsewhere
✅ **Reliable:** Cloudflare-backed infrastructure
✅ **Free:** No extra cost for DNS management
✅ **Simple UI:** Clean interface, easy to manage
✅ **Global CDN:** Distributed DNS servers worldwide

### **Perfect for SuoPay:**

Your frontend is on Vercel, so managing DNS there makes sense:
- One place for deployment + DNS
- Fast updates
- Integrated with your existing infrastructure

---

## 🎯 After DNS Propagates (5-30 minutes)

### **Step 7: Check AWS SES Verification Status**

1. Go to AWS SES Console: https://console.aws.amazon.com/ses/
2. Click **Identities** (left sidebar)
3. Click **suopay.io**
4. Check these statuses:

```
Identity status:          🟢 Verified
DKIM status:              🟢 Successful  
Custom MAIL FROM status:  🟢 Successful
```

If all three are green ✅ - **You're ready to send emails!**

⚠️ **If still "Pending" after 30 minutes:**
- Wait another 30 minutes (total 1 hour)
- Check DNS with `dig` commands to verify records are live
- Refresh AWS SES page

---

## 🚀 Next Steps After Verification

Once your domain is verified (all statuses green):

### **1. Create SMTP Credentials**

```bash
1. AWS SES Console → SMTP settings (left sidebar)
2. Click "Create SMTP credentials"
3. IAM User Name: suopay-smtp-user
4. Click "Create user"
5. SAVE the SMTP username and password (shown only once!)
```

### **2. Configure Heroku**

```bash
heroku config:set \
  EMAIL_PROVIDER=ses \
  SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com \
  SES_SMTP_PORT=587 \
  SES_SMTP_USER=YOUR_SMTP_USERNAME \
  SES_SMTP_PASSWORD=YOUR_SMTP_PASSWORD \
  FROM_EMAIL=noreply@suopay.io \
  --app suopay-backend
```

### **3. Test Email Sending**

```bash
curl -X POST https://suopay-backend-a204d4816960.herokuapp.com/invoices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "customer_name": "Test Customer",
    "customer_email": "your-email@example.com",
    "amount": 10000,
    "lines": [{"description": "Test Item", "quantity": 1, "unit_price": 10000}]
  }'
```

Check your email inbox! 📧

---

## 🐛 Troubleshooting

### **Issue: Can't find "Add" button**

**Solution:**
1. Make sure you're on the domain details page: https://vercel.com/dashboard/domains/suopay.io
2. Scroll down to **DNS Records** section
3. The **Add** button should be on the right side of that section

### **Issue: "Record already exists"**

**Solution:**
1. Check if there's a conflicting record (same type and name)
2. Click **⋮** (three dots) next to the conflicting record
3. Select **Delete**
4. Add the new record

### **Issue: TXT record value appears with quotes**

**Solution:**
- Vercel may add quotes automatically
- This is fine! AWS SES will still recognize it
- The actual DNS query will return the correct value

### **Issue: DNS not propagating**

**Solution:**
1. Wait 30 minutes (Vercel is usually faster)
2. Check if records appear in Vercel dashboard
3. Use `dig` command to check:
   ```bash
   dig mail.suopay.io MX
   ```
4. If no results after 1 hour, try deleting and re-adding the record

---

## 📞 Need Help?

### **Vercel Support:**
- **Help Center:** https://vercel.com/help
- **Support:** https://vercel.com/support
- **Docs:** https://vercel.com/docs/concepts/projects/domains

**Or Message Me:**
Share a screenshot of your Vercel DNS Records section and I'll help!

---

## ✅ Summary

**What you need to do:**
1. Login to Vercel: https://vercel.com/login
2. Go to Domains → suopay.io → DNS Records section
3. Add 6 DNS records (3 CNAME, 1 MX, 2 TXT)
4. Wait 5-30 minutes for DNS propagation ⚡
5. Check AWS SES Console for "Verified" status
6. Create SMTP credentials
7. Configure Heroku
8. Start sending unlimited emails! 🚀

**Estimated time:** 
- Adding records: 10 minutes
- DNS propagation: 5-30 minutes (Vercel is FAST!)
- Total setup: Usually complete in 30-45 minutes

---

## 🎯 Quick Reference

```
Login: https://vercel.com/login
Domain: https://vercel.com/dashboard/domains/suopay.io

Records to add:
- 3 CNAME (DKIM): ._domainkey subdomains
- 1 MX: mail subdomain (priority 10)
- 2 TXT: mail (SPF) and _dmarc (DMARC policy)

No quotes on TXT values
No .suopay.io suffix on Names
Wait 5-30 minutes for propagation
```

---

**Ready to start?** Go to https://vercel.com/dashboard/domains/suopay.io and follow the steps above!

Let me know when you've added the records, and I'll help you verify them! 🎉

Last updated: October 22, 2025
