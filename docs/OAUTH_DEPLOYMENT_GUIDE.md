# OAuth 2.0 Deployment Guide - Quick Start

## ✅ Step 1: Google Cloud Console (IN PROGRESS)

You should have the Google Cloud Console open. Complete these steps:

1. **Create Project**: `suopay-oauth`
2. **Enable Google+ API**
3. **Configure OAuth Consent Screen**:
   - App name: SuoPay
   - Support email: support@suoops.com
   - Developer contact: info@suoops.com
4. **Create OAuth Credentials**:
   - Type: Web application
   - Name: SuoPay Production
   - Redirect URIs:
     - `https://api.suoops.com/auth/oauth/google/callback`
     - `http://localhost:8000/auth/oauth/google/callback`

5. **COPY THE CREDENTIALS** you receive!

---

## Step 2: Configure Heroku Environment Variables

Once you have your **Client ID** and **Client Secret**, run these commands:

```bash
# Set Google OAuth Client ID (replace with your actual value)
heroku config:set GOOGLE_CLIENT_ID="YOUR_CLIENT_ID.apps.googleusercontent.com" --app suoops-backend

# Set Google OAuth Client Secret (replace with your actual value)
heroku config:set GOOGLE_CLIENT_SECRET="GOCSPX-YOUR_SECRET" --app suoops-backend

# Generate and set OAuth state secret
heroku config:set OAUTH_STATE_SECRET="$(openssl rand -hex 32)" --app suoops-backend
```

**Verify configuration:**
```bash
heroku config --app suoops-backend | grep -E '(GOOGLE_|OAUTH_)'
```

---

## Step 3: Deploy to Heroku

```bash
# Commit OAuth changes
git add .
git commit -m "feat: Deploy OAuth 2.0 with authlib dependency"

# Push to GitHub
git push origin main

# Deploy to Heroku
git push heroku main
```

---

## Step 4: Test OAuth Flow

### Test Providers Endpoint
```bash
curl https://api.suoops.com/auth/oauth/providers
```

**Expected response:**
```json
{
  "providers": [
    {
      "name": "google",
      "display_name": "Google",
      "enabled": true,
      "supports_refresh": true,
      "icon_url": "https://www.google.com/favicon.ico"
    }
  ]
}
```

### Test OAuth Login (in browser)
```bash
open https://api.suoops.com/auth/oauth/google/login
```

**What should happen:**
1. Redirects to Google sign-in page
2. You sign in with Google
3. Google redirects back to your callback URL
4. You receive JWT tokens

---

## Step 5: Update NRS Registration

✅ Update your NRS registration form:

**SSO Compatibility:** YES ✅
- **Provider:** Google OAuth 2.0 (OpenID Connect)
- **Status:** DEPLOYED
- **Documentation:** https://ayibatonye-ikemike.github.io/suoops-backend/
- **Setup Guide:** docs/oauth-setup-guide.md

---

## Troubleshooting

### "Provider not enabled" error
- **Cause:** Environment variables not set
- **Fix:** Check Heroku config vars are set correctly

### "Invalid redirect URI" error
- **Cause:** Callback URL mismatch
- **Fix:** Ensure `https://api.suoops.com/auth/oauth/google/callback` is in Google Console

### "Failed to exchange code for token" error
- **Cause:** Invalid Client Secret or ID
- **Fix:** Verify credentials in Heroku config match Google Console

---

## Quick Reference

**Google Cloud Console:** https://console.cloud.google.com/

**OAuth Endpoints:**
- List providers: `GET https://api.suoops.com/auth/oauth/providers`
- Login: `GET https://api.suoops.com/auth/oauth/google/login`
- Callback: `GET https://api.suoops.com/auth/oauth/google/callback`

**Documentation:**
- Setup guide: `docs/oauth-setup-guide.md`
- Security compliance: `SECURITY-COMPLIANCE.md`
- Accreditation readiness checklist: `docs/accreditation-readiness-checklist.md` (replaces legacy NRS checklist)

---

## Next Steps After Deployment

1. ✅ Test OAuth flow end-to-end
2. 📱 Integrate with frontend ("Sign in with Google" button)
3. 🔐 Schedule VAPT assessment (Q1 2026)
4. 📋 Submit NRS registration form

---

**Ready to proceed?**

Once you have your Google OAuth credentials (Client ID and Client Secret), paste them here and I'll configure Heroku for you!
