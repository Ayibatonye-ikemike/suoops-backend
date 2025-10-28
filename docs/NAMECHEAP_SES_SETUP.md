# Namecheap DNS Setup for Amazon SES - Step by Step

## 🎯 Goal
Add 6 DNS records to your `suoops.com` domain in Namecheap for Amazon SES email verification.

---

## 📝 Step-by-Step Instructions

### **Step 1: Login to Namecheap**

1. Go to: https://www.namecheap.com/myaccount/login/
2. Enter your **username** and **password**
3. Click **Sign In**

---

### **Step 2: Access Domain DNS Settings**

1. Click **Domain List** in the left sidebar
2. Find **suoops.com** in the list
3. Click **MANAGE** button next to `suoops.com`
4. Click the **Advanced DNS** tab (at the top)

You should see a page with "HOST RECORDS" section.

---

### **Step 3: Add DKIM Records (3 CNAME Records)**

Click **ADD NEW RECORD** button for each of these:

#### **DKIM Record 1:**
```
Type: CNAME Record
Host: iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey
Value: iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com
TTL: Automatic
```

**Exact Steps:**
1. Click **ADD NEW RECORD**
2. **Type:** Select `CNAME Record` from dropdown
3. **Host:** Enter `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey`
4. **Value:** Enter `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`
5. **TTL:** Leave as `Automatic`
6. Click the **✓ (checkmark)** button to save

#### **DKIM Record 2:**
```
Type: CNAME Record
Host: flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey
Value: flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com
TTL: Automatic
```

**Exact Steps:**
1. Click **ADD NEW RECORD** again
2. **Type:** Select `CNAME Record`
3. **Host:** Enter `flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey`
4. **Value:** Enter `flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com`
5. **TTL:** Leave as `Automatic`
6. Click the **✓ (checkmark)** button to save

#### **DKIM Record 3:**
```
Type: CNAME Record
Host: 6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey
Value: 6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com
TTL: Automatic
```

**Exact Steps:**
1. Click **ADD NEW RECORD** again
2. **Type:** Select `CNAME Record`
3. **Host:** Enter `6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey`
4. **Value:** Enter `6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com`
5. **TTL:** Leave as `Automatic`
6. Click the **✓ (checkmark)** button to save

---

### **Step 4: Add MX Record (1 Record)**

```
Type: MX Record
Host: mail
Value: feedback-smtp.eu-north-1.amazonses.com
Priority: 10
TTL: Automatic
```

**Exact Steps:**
1. Click **ADD NEW RECORD**
2. **Type:** Select `MX Record` from dropdown
3. **Host:** Enter `mail`
4. **Value:** Enter `feedback-smtp.eu-north-1.amazonses.com`
5. **Priority:** Enter `10`
6. **TTL:** Leave as `Automatic`
7. Click the **✓ (checkmark)** button to save

---

### **Step 5: Add SPF Record (TXT Record for mail.suoops.com)**

```
Type: TXT Record
Host: mail
Value: v=spf1 include:amazonses.com ~all
TTL: Automatic
```

**Exact Steps:**
1. Click **ADD NEW RECORD**
2. **Type:** Select `TXT Record` from dropdown
3. **Host:** Enter `mail`
4. **Value:** Enter `v=spf1 include:amazonses.com ~all`
   - ⚠️ **Do NOT include quotes** - Namecheap adds them automatically
5. **TTL:** Leave as `Automatic`
6. Click the **✓ (checkmark)** button to save

---

### **Step 6: Add DMARC Record (TXT Record)**

```
Type: TXT Record
Host: _dmarc
Value: v=DMARC1; p=none;
TTL: Automatic
```

**Exact Steps:**
1. Click **ADD NEW RECORD**
2. **Type:** Select `TXT Record` from dropdown
3. **Host:** Enter `_dmarc`
4. **Value:** Enter `v=DMARC1; p=none;`
   - ⚠️ **Do NOT include quotes** - Namecheap adds them automatically
5. **TTL:** Leave as `Automatic`
6. Click the **✓ (checkmark)** button to save

---

## ✅ Verification Checklist

After adding all records, your DNS should have:

- [x] **3 CNAME Records** with `._domainkey` in the Host
- [x] **1 MX Record** for `mail` subdomain
- [x] **2 TXT Records** (one for `mail`, one for `_dmarc`)

**Total: 6 new DNS records**

---

## 🕐 What Happens Next?

### **Immediate (Now):**
- You'll see all 6 records in your Namecheap Advanced DNS page
- They show as "Pending" or with orange dots

### **15 minutes - 2 hours later:**
- DNS records propagate globally
- Records become active (green checkmarks)

### **In AWS SES Console:**
1. Go to: https://console.aws.amazon.com/ses/
2. Click **Identities** → **suoops.com**
3. **Status** changes from "Pending verification" → "Verified" ✅
4. **DKIM status** changes from "Pending" → "Successful" ✅
5. **Custom MAIL FROM** changes from "Pending" → "Successful" ✅

---

## 🔍 Verify Your DNS Records

### **Option 1: Check in Namecheap (Instant)**

In the Advanced DNS page, you should see all 6 records listed. Each record should have:
- Green checkmark icon (after saving)
- Correct Type, Host, and Value

### **Option 2: Check DNS Propagation (15 mins - 48 hours)**

Run these commands in your terminal:

```bash
# Check DKIM Record 1
dig iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suoops.com CNAME

# Check DKIM Record 2
dig flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey.suoops.com CNAME

# Check DKIM Record 3
dig 6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey.suoops.com CNAME

# Check MX Record
dig mail.suoops.com MX

# Check SPF Record
dig mail.suoops.com TXT

# Check DMARC Record
dig _dmarc.suoops.com TXT
```

**Expected results:**
- CNAME records should show `.dkim.amazonses.com` in the answer
- MX record should show `feedback-smtp.eu-north-1.amazonses.com`
- TXT records should show `v=spf1` and `v=DMARC1`

### **Option 3: Use Online Tool**

1. Go to: https://mxtoolbox.com/SuperTool.aspx
2. Enter: `iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey.suoops.com`
3. Select **CNAME Lookup**
4. Should show: `iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com`

Repeat for other records.

---

## ⚠️ Common Namecheap-Specific Issues

### **Issue 1: "Cannot add duplicate record"**

**Cause:** A similar record already exists
**Fix:** 
1. Scroll through existing records
2. Find the conflicting record
3. Delete it (click the trash icon)
4. Add the new record again

### **Issue 2: Host field showing error "Invalid format"**

**Cause:** Including `.suoops.com` in the Host field
**Fix:**
- ❌ Wrong: `mail.suoops.com`
- ✅ Correct: `mail`

Namecheap automatically appends `.suoops.com`

### **Issue 3: TXT record value has extra quotes**

**Cause:** Adding quotes manually
**Fix:**
- ❌ Wrong: `"v=spf1 include:amazonses.com ~all"`
- ✅ Correct: `v=spf1 include:amazonses.com ~all`

Namecheap adds quotes automatically!

### **Issue 4: MX record format issue**

**Namecheap MX Record Format:**
- **Host:** `mail`
- **Value:** `feedback-smtp.eu-north-1.amazonses.com` (without priority)
- **Priority:** `10` (separate field)

Don't include `10` in the Value field!

### **Issue 5: Records not saving**

**Solutions:**
1. Click the **✓ (green checkmark)** button after each record
2. If page times out, refresh and add records again
3. Try adding records one at a time instead of all at once

---

## 📸 Visual Guide (What You Should See)

### **After Adding All Records:**

Your Advanced DNS page should look like this:

```
HOST RECORDS

Type        Host                                              Value                                                    TTL
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
CNAME       iu5cwz57dsyf2d4owslq3dg3dvw6verk._domainkey      iu5cwz57dsyf2d4owslq3dg3dvw6verk.dkim.amazonses.com     Automatic
CNAME       flhynideglr2zsjvynjv3j4w2i5hjzcl._domainkey      flhynideglr2zsjvynjv3j4w2i5hjzcl.dkim.amazonses.com     Automatic
CNAME       6dc424alpsfgha7hbqoomnfdfsnzbdfx._domainkey      6dc424alpsfgha7hbqoomnfdfsnzbdfx.dkim.amazonses.com     Automatic
MX          mail                                               feedback-smtp.eu-north-1.amazonses.com (Priority: 10)    Automatic
TXT         mail                                               v=spf1 include:amazonses.com ~all                        Automatic
TXT         _dmarc                                             v=DMARC1; p=none;                                        Automatic
```

**Note:** Your existing records (A, CNAME for www, etc.) will still be there - that's normal!

---

## 🎯 After DNS Propagates (1-48 hours)

### **Step 7: Check AWS SES Verification Status**

1. Go to AWS SES Console: https://console.aws.amazon.com/ses/
2. Click **Identities** (left sidebar)
3. Click **suoops.com**
4. Check these statuses:

```
Identity status:          🟢 Verified
DKIM status:              🟢 Successful  
Custom MAIL FROM status:  🟢 Successful
```

If all three are green ✅ - **You're ready to send emails!**

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
  FROM_EMAIL=noreply@suoops.com \
  --app suoops-backend
```

### **3. Test Email Sending**

```bash
curl -X POST https://suoops-backend.herokuapp.com/invoices \
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

## 📞 Need Help?

### **Namecheap Support:**
- Live Chat: https://www.namecheap.com/support/live-chat/
- Support Ticket: https://support.namecheap.com/
- Phone: +1.323.375.2822

**Tell them:** "I need help adding DNS records for Amazon SES email authentication"

### **Or Message Me:**
Share a screenshot of:
1. Your Namecheap Advanced DNS page
2. Any error messages you see

I'll help you fix it!

---

## ✅ Summary

**What you need to do:**
1. Login to Namecheap
2. Go to Domain List → Manage suoops.com → Advanced DNS
3. Add 6 DNS records (3 CNAME, 1 MX, 2 TXT)
4. Wait 15 mins - 48 hours for DNS propagation
5. Check AWS SES Console for "Verified" status
6. Create SMTP credentials
7. Configure Heroku
8. Start sending unlimited emails! 🚀

**Estimated time:** 
- Adding records: 10-15 minutes
- DNS propagation: 15 minutes - 48 hours
- Total setup: Usually complete in 1-2 hours

---

**Ready to start?** Go to https://www.namecheap.com/myaccount/login/ and follow the steps above!

Let me know when you've added the records, and I'll help you verify them! 🎉

Last updated: October 22, 2025
