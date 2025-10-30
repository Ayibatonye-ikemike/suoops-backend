# ControlD Whitelist Configuration Guide

## 🎯 Goal
Allow `api.suoops.com` to resolve correctly while keeping ControlD active for other domains.

---

## 📋 Step-by-Step Instructions

### Method 1: Add to Whitelist (Recommended)

#### Option A: Via ControlD Dashboard (Web)

1. **Open ControlD Dashboard**
   - Go to: https://controld.com/dashboard
   - Log in with your account

2. **Navigate to Filters**
   - Click on "Filters" or "Custom Rules" in the sidebar
   - Or go to: https://controld.com/dashboard/filters

3. **Add Custom Rule**
   - Click "Add Rule" or "Add Custom Rule"
   - Select "Allow" or "Bypass"

4. **Configure Rule**
   ```
   Domain: api.suoops.com
   Action: Allow / Bypass / Whitelist
   Description: SuoOps production API
   ```

5. **Save and Apply**
   - Click "Save"
   - Wait 10-30 seconds for propagation

6. **Verify**
   ```bash
   # Flush DNS cache
   sudo dscacheutil -flushcache
   sudo killall -HUP mDNSResponder
   
   # Test resolution
   dig api.suoops.com +short
   # Should NOT show 0.0.0.0
   ```

#### Option B: Via ControlD App (macOS)

1. **Open ControlD App**
   - Look for ControlD icon in menu bar
   - Click to open

2. **Access Settings**
   - Click "Settings" or gear icon
   - Look for "Custom Rules" or "Filters"

3. **Add Domain to Whitelist**
   ```
   Add: api.suoops.com
   Type: Whitelist/Allow
   ```

4. **Apply Changes**
   - Click "Apply" or "Save"
   - App should restart DNS resolver

5. **Test**
   ```bash
   dig api.suoops.com +short
   ```

---

### Method 2: Temporary Pause (Quick Test)

If you just want to test quickly:

1. **Open ControlD App**
   - Click ControlD icon in menu bar

2. **Pause Protection**
   - Look for "Pause" button
   - Select "Pause for 1 hour" or "Pause indefinitely"

3. **Flush DNS Cache**
   ```bash
   sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
   ```

4. **Run Test**
   ```bash
   cd /Users/ayibatonyeikemike/mywork/suopay.io
   ./test_domain.sh
   ```

5. **Re-enable Later**
   - Click ControlD icon → "Resume"

---

### Method 3: Profile Configuration (Advanced)

If using ControlD profiles:

1. **Find Active Profile**
   - Open ControlD dashboard
   - Check which profile is active (Home, Work, etc.)

2. **Edit Profile**
   - Click on active profile
   - Go to "Custom Rules" section

3. **Add Whitelisted Domain**
   ```
   Domain: api.suoops.com
   Rule: Bypass filtering
   Priority: High
   ```

4. **Save Profile**

---

### Method 4: DNS Override (Alternative)

If whitelist doesn't work, temporarily override DNS:

```bash
# Switch to Cloudflare DNS (bypasses ControlD)
sudo networksetup -setdnsservers Wi-Fi 1.1.1.1 1.0.0.1

# Test
dig api.suoops.com +short
./test_domain.sh

# Switch back to ControlD (get ControlD DNS IPs first)
sudo networksetup -setdnsservers Wi-Fi <CONTROLD_DNS_IP>
```

---

## 🧪 Verification Steps

After configuring whitelist:

### 1. Flush DNS Cache
```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
echo "✅ DNS cache cleared"
```

### 2. Test DNS Resolution
```bash
echo "Testing api.suoops.com resolution..."
DIG_RESULT=$(dig api.suoops.com +short)
echo "Result: $DIG_RESULT"

if echo "$DIG_RESULT" | grep -q "0.0.0.0"; then
    echo "❌ Still blocked - whitelist not applied yet"
else
    echo "✅ Whitelist working!"
fi
```

### 3. Test API Endpoint
```bash
echo "Testing API health check..."
curl -s https://api.suoops.com/healthz
# Should return: {"status":"ok"}
```

### 4. Run Full Test Suite
```bash
cd /Users/ayibatonyeikemike/mywork/suopay.io
./test_domain.sh
```

---

## 🔍 Troubleshooting

### Problem: Whitelist Not Working

**Check 1: DNS Propagation**
```bash
# Wait 30 seconds after saving whitelist
sleep 30
sudo dscacheutil -flushcache
dig api.suoops.com +short
```

**Check 2: Correct Domain Format**
- Use: `api.suoops.com` (no https://, no trailing /)
- NOT: `https://api.suoops.com/`
- NOT: `*.suoops.com` (unless you want wildcard)

**Check 3: Rule Priority**
- Whitelist rules should have HIGH priority
- Block rules might override whitelist if higher priority

**Check 4: Profile Active**
- Ensure correct ControlD profile is active
- Whitelist must be in ACTIVE profile

### Problem: Still Shows 0.0.0.0

**Solution A: Restart ControlD**
```bash
# Kill and restart ControlD service
# (Command varies by ControlD installation)
```

**Solution B: Use Alternative DNS Temporarily**
```bash
# Use Google DNS for testing
sudo networksetup -setdnsservers Wi-Fi 8.8.8.8 8.8.4.4
```

**Solution C: Check ControlD Logs**
- Open ControlD app
- Look for logs/activity
- See if api.suoops.com is being blocked

### Problem: Whitelist Keeps Resetting

**Possible Causes:**
1. Profile syncing from cloud
2. Multiple devices with conflicting settings
3. ControlD subscription tier limitations

**Solution:**
- Check ControlD plan (some plans limit custom rules)
- Disable profile sync if needed
- Contact ControlD support

---

## 🚀 Quick Commands Reference

```bash
# 1. Flush DNS cache
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder

# 2. Test DNS resolution
dig api.suoops.com +short

# 3. Test API health
curl -s https://api.suoops.com/healthz

# 4. Run full test suite
cd /Users/ayibatonyeikemike/mywork/suopay.io && ./test_domain.sh

# 5. Test QR verification endpoint
curl -s https://api.suoops.com/invoices/TEST-123/verify

# 6. Check current DNS servers
scutil --dns | grep 'nameserver\[0\]'

# 7. Switch to Google DNS (bypass ControlD)
sudo networksetup -setdnsservers Wi-Fi 8.8.8.8 8.8.4.4

# 8. Switch to Cloudflare DNS (bypass ControlD)
sudo networksetup -setdnsservers Wi-Fi 1.1.1.1 1.0.0.1
```

---

## 📞 Need Help?

### ControlD Resources
- Dashboard: https://controld.com/dashboard
- Support: https://controld.com/support
- Docs: https://docs.controld.com

### Alternative: Bypass ControlD for Testing
```bash
# Option 1: Pause ControlD (via app)
# Option 2: Use direct Heroku URL
curl https://suoops-backend-e4a267e41e92.herokuapp.com/healthz

# Option 3: Use mobile hotspot (bypasses local DNS)
```

---

## ✅ Success Indicators

When whitelist is working correctly:

```bash
$ dig api.suoops.com +short
# Shows actual IP (NOT 0.0.0.0)

$ curl -s https://api.suoops.com/healthz
{"status":"ok"}

$ ./test_domain.sh
# All tests pass ✅
```

---

## 🎯 Why Whitelist?

### Benefits:
- ✅ Keep ControlD active for security
- ✅ Allow your own domains
- ✅ No need to disable protection
- ✅ Permanent solution

### Use Cases:
- Development/testing your own APIs
- Accessing business tools
- Allowing specific services
- Bypassing false positives

---

## 📝 Notes

- Whitelist changes may take 10-30 seconds to propagate
- Always flush DNS cache after changes
- Some ControlD plans limit custom rules
- Test with `dig` before testing with `curl`
- Mobile hotspot bypasses ControlD (good for emergency testing)

---

**Once whitelisted, all your QR codes will work perfectly!** 🎉
