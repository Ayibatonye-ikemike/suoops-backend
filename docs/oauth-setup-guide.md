# OAuth 2.0 / SSO Setup Guide

## Overview
This guide walks through setting up Google OAuth 2.0 for Single Sign-On (SSO) in the SuoPay API.

## Architecture
- **Provider Pattern**: Abstract `OAuthProvider` base class supports multiple providers (Google, Microsoft, Apple)
- **Current Implementation**: Google OAuth 2.0 with OpenID Connect
- **Security**: CSRF state tokens, one-time use validation, secure random generation
- **Token Management**: JWT access tokens (24hr), refresh tokens (14 days)
- **User Provisioning**: Auto-create users from OAuth, update existing users

## Google OAuth Setup

### 1. Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Enter project name: `suopay-oauth`
4. Click "Create"

### 2. Enable Google+ API
1. In the navigation menu, go to "APIs & Services" → "Library"
2. Search for "Google+ API"
3. Click on it and click "Enable"

### 3. Create OAuth 2.0 Credentials
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - User Type: **External**
   - App name: **SuoPay**
   - User support email: **support@suoops.com**
   - Developer contact: **info@suoops.com**
   - Scopes: `openid`, `email`, `profile`
   - Test users: Add your admin email
4. Application type: **Web application**
5. Name: `SuoPay Production`
6. Authorized redirect URIs:
   - `https://api.suoops.com/auth/oauth/google/callback`
   - `http://localhost:8000/auth/oauth/google/callback` (for local testing)
7. Click "Create"
8. **Copy the Client ID and Client Secret** (you'll need these for environment variables)

### 4. Configure Heroku Environment Variables
```bash
# Set Google OAuth credentials
heroku config:set GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com" --app suoops-backend
heroku config:set GOOGLE_CLIENT_SECRET="GOCSPX-xxx" --app suoops-backend

# Generate and set secure OAuth state secret
heroku config:set OAUTH_STATE_SECRET="$(openssl rand -hex 32)" --app suoops-backend

# Verify configuration
heroku config --app suoops-backend | grep -E '(GOOGLE_|OAUTH_)'
```

### 5. Test OAuth Flow

#### Local Testing
```bash
# Start local server
uvicorn app.api.main:app --reload

# Navigate to OAuth login
open http://localhost:8000/auth/oauth/google/login?redirect_uri=http://localhost:3000/dashboard

# Complete Google sign-in flow
# Should redirect back with JWT tokens in callback response
```

#### Production Testing
```bash
# Navigate to production OAuth login
open https://api.suoops.com/auth/oauth/google/login?redirect_uri=https://app.suoops.com/dashboard

# Complete Google sign-in flow
# Should redirect to dashboard with tokens
```

## API Endpoints

### List Available OAuth Providers
```http
GET /auth/oauth/providers
```

**Response:**
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

### Initiate OAuth Flow
```http
GET /auth/oauth/{provider}/login?redirect_uri={frontend_url}
```

**Parameters:**
- `provider`: OAuth provider name (e.g., `google`)
- `redirect_uri` (optional): Frontend URL to redirect after authentication

**Response:** HTTP 302 redirect to OAuth provider

### OAuth Callback
```http
GET /auth/oauth/{provider}/callback?code={auth_code}&state={csrf_state}
```

**Parameters:**
- `code`: Authorization code from OAuth provider
- `state`: CSRF state token (auto-validated)

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "redirect_uri": "https://app.suoops.com/dashboard"
}
```

### Revoke OAuth Access (Future)
```http
POST /auth/oauth/{provider}/revoke
Authorization: Bearer {access_token}
```

## Security Features

### CSRF Protection
- Cryptographically secure state tokens generated with `secrets.token_hex(16)`
- One-time use validation (state popped after validation)
- State contains redirect URI to prevent open redirect attacks

### Token Security
- JWT access tokens: 24-hour expiry
- JWT refresh tokens: 14-day expiry
- HS256 signing algorithm with secure secret

### User Provisioning
- OAuth users created with empty `password_hash` (OAuth-only accounts)
- Existing users updated with `last_login` timestamp
- Email verified automatically from OAuth provider

## Production Deployment Checklist

- [x] OAuth routes registered in `app/api/main.py`
- [ ] authlib dependency installed (run in production: `pip install authlib`)
- [ ] Google OAuth app created with production callback URL
- [ ] Environment variables configured in Heroku
- [ ] Local testing completed
- [ ] Production testing completed
- [ ] Frontend OAuth integration completed
- [ ] State store migrated to Redis (current: in-memory)
- [ ] Rate limiting configured for OAuth endpoints
- [ ] Audit logging enabled for OAuth events

## Future Enhancements

### Microsoft OAuth
```python
class MicrosoftOAuthProvider(OAuthProvider):
    authorization_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    user_info_url = "https://graph.microsoft.com/v1.0/me"
    scopes = ["openid", "email", "profile"]
```

### Apple OAuth
```python
class AppleOAuthProvider(OAuthProvider):
    authorization_url = "https://appleid.apple.com/auth/authorize"
    token_url = "https://appleid.apple.com/auth/token"
    user_info_url = "https://appleid.apple.com/auth/userinfo"
    scopes = ["openid", "email", "name"]
```

### State Store Migration to Redis
```python
# Replace in-memory dict with Redis
import redis.asyncio as redis

oauth_states = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True
)

# Set state with TTL
await oauth_states.setex(state, 600, redirect_uri)  # 10 minutes

# Get and delete state (atomic)
redirect_uri = await oauth_states.getdel(state)
```

## Troubleshooting

### "Invalid OAuth state" Error
- **Cause**: State token expired or already used
- **Solution**: Restart OAuth flow from `/auth/oauth/google/login`

### "Provider not found" Error
- **Cause**: Google credentials not configured
- **Solution**: Check `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in Heroku config

### "Failed to exchange code for token" Error
- **Cause**: Invalid authorization code or callback URL mismatch
- **Solution**: Verify callback URL matches Google Cloud Console configuration

### Callback URL Not Working
- **Cause**: Redirect URI not whitelisted in Google Cloud Console
- **Solution**: Add `https://api.suoops.com/auth/oauth/google/callback` to authorized URIs

## Support
- **General Inquiries**: info@suoops.com
- **Technical Support**: support@suoops.com
- **Phone/WhatsApp**: +234 816 208 8344
- **Business Hours**: Mon-Fri 9AM-6PM WAT
- **Emergency**: 24/7 for P1 incidents

## References
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [OpenID Connect Specification](https://openid.net/connect/)
- [authlib Documentation](https://docs.authlib.org/)
- [OAuth 2.0 RFC 6749](https://datatracker.ietf.org/doc/html/rfc6749)
