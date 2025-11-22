# OAuth 2.0 Security Audit & Compliance Report

**Date:** November 22, 2025  
**System:** SuoOps OAuth Implementation  
**Scope:** Google OAuth 2.0 Integration  
**Status:** 🟡 MODERATE RISK - Immediate Action Required

---

## Executive Summary

This audit evaluates the SuoOps OAuth implementation against Google's OAuth 2.0 security best practices and industry standards. While the implementation follows authorization code flow correctly, **several critical security vulnerabilities** exist that must be addressed before production launch.

### Risk Assessment

| Category | Status | Risk Level |
|----------|--------|------------|
| **Credential Security** | 🔴 CRITICAL | HIGH |
| **Token Management** | 🟠 INCOMPLETE | MEDIUM |
| **Authorization Flow** | 🟢 COMPLIANT | LOW |
| **Scope Management** | 🟡 NEEDS IMPROVEMENT | MEDIUM |
| **Client Configuration** | 🟢 COMPLIANT | LOW |

---

## 1. Critical Security Issues

### 🔴 CRITICAL: Hardcoded Client Credentials in Logs

**Issue:** `oauth_service.py` logs full client secrets in debug mode (line 131-140):

```python
logger.error(
    f"[DEBUG] FULL TOKEN EXCHANGE PAYLOAD:\n"
    f"  client_secret: {self.client_secret[:10]}...{self.client_secret[-5:]}\n"
    f"  code: {code}\n"
)
```

**Risk:** 
- OAuth client secrets exposed in Heroku logs
- Authorization codes exposed (single-use but still sensitive)
- Potential secret leakage in log aggregation systems
- Violates Google's credential security guidelines

**Google Guideline Violated:**
> "Handle client credentials securely... Do not hardcode the credentials, commit them to a code repository or **publish them publicly**."

**Recommendation:** 
- ✅ **IMMEDIATE:** Remove or redact all credential logging
- ✅ **IMMEDIATE:** Rotate current Google OAuth credentials
- ✅ Use code hashes only (never raw codes)
- ✅ Never log client secrets, even partially

**Action Required:**
```python
# REMOVE THIS SECTION ENTIRELY
logger.error(
    f"[DEBUG] FULL TOKEN EXCHANGE PAYLOAD:\n"
    ...
)

# REPLACE WITH:
logger.info(
    f"Token exchange attempt | provider=google code_hash={hash(code)} "
    f"client_id={self.client_id[:20]}..."
)
```

---

### 🟠 MEDIUM: No OAuth Refresh Token Storage

**Issue:** The system obtains refresh tokens but never stores them:

```python
# tokens returned but not persisted
tokens = await oauth_service.authenticate_with_code(provider, code)
```

**Risk:**
- Users must re-authenticate every session
- Cannot revoke OAuth access properly
- Cannot detect token revocation events
- Poor user experience (frequent re-logins)

**Google Guideline Violated:**
> "Handle user tokens securely. User tokens include both refresh tokens and access tokens... Store tokens securely at rest."

**Current Flow:**
1. User authenticates via Google ✅
2. Backend gets refresh token ✅
3. Backend generates JWT tokens ✅
4. **Backend discards Google refresh token** ❌
5. User must re-authenticate next session ❌

**Recommendation:**
- ✅ Create `oauth_tokens` table to store encrypted refresh tokens
- ✅ Link tokens to user accounts with provider information
- ✅ Implement token encryption at rest (use Fernet or similar)
- ✅ Add token expiration tracking
- ✅ Implement token revocation endpoints

**Schema Required:**
```python
class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String(50), nullable=False)  # "google"
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)
    token_type = Column(String(50), default="bearer")
    expires_at = Column(DateTime(timezone=True))
    scopes = Column(JSON)  # ["openid", "email", "profile"]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_oauth_tokens_user_provider", "user_id", "provider", unique=True),
    )
```

---

### 🟡 MODERATE: Aggressive Scope Requests

**Issue:** All OAuth scopes requested upfront without justification:

```python
@property
def scopes(self) -> list[str]:
    return ["openid", "email", "profile"]
```

**Risk:**
- Violates principle of least privilege
- May trigger additional Google verification requirements
- Poor user experience (scary consent screen)
- Not following incremental authorization

**Google Guideline Violated:**
> "Use incremental authorization to request appropriate OAuth scopes when the functionality is needed... You should not request access to data when the user first authenticates, unless it is essential."

**Current Behavior:**
- All scopes requested at login ❌
- No justification shown to user ❌
- No graceful degradation if user denies scopes ❌

**Recommendation:**
- ✅ Request only `openid` and `email` for basic authentication
- ✅ Request `profile` scope only when user accesses profile features
- ✅ Implement scope-specific error handling
- ✅ Add user-facing explanations for each scope

**Implementation:**
```python
# Minimal scopes for authentication
CORE_SCOPES = ["openid", "email"]

# Optional scopes requested in context
PROFILE_SCOPES = ["profile"]  # Request when user visits profile page

def get_authorization_url(self, state: str, additional_scopes: list[str] = None) -> str:
    base_scopes = self.CORE_SCOPES
    if additional_scopes:
        base_scopes = base_scopes + additional_scopes
    
    params = {
        "scope": " ".join(base_scopes),
        # ... rest of params
    }
```

---

### 🟡 MODERATE: Missing Token Revocation Handling

**Issue:** No mechanism to detect or handle token revocation:

```python
@router.post("/{provider}/revoke")
async def revoke_oauth_access(...):
    # TODO: Implement OAuth token storage and revocation
    return {"status": "not_implemented"}
```

**Risk:**
- Cannot respond to user revoking access via Google Account settings
- Cannot clean up orphaned data
- No Cross-Account Protection integration
- Violates user privacy expectations

**Google Guideline Violated:**
> "If your app has requested a refresh token for offline access, you must also handle their invalidation or expiration... To be notified of token revocation, integrate with the Cross-Account Protection service."

**Recommendation:**
- ✅ Implement token revocation endpoint
- ✅ Call Google's token revocation API
- ✅ Clean up stored refresh tokens
- ✅ Integrate Cross-Account Protection (RISC)
- ✅ Add webhook for Google revocation events

**Implementation:**
```python
async def revoke_oauth_token(user_id: int, provider: str, db: Session):
    """Revoke OAuth access and clean up tokens."""
    token = db.query(OAuthToken).filter(
        OAuthToken.user_id == user_id,
        OAuthToken.provider == provider,
        OAuthToken.revoked_at == None
    ).first()
    
    if not token:
        return
    
    # Call Google's revocation endpoint
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": decrypt_token(token.refresh_token_encrypted)}
        )
    
    # Mark as revoked in database
    token.revoked_at = datetime.now(timezone.utc)
    db.commit()
```

---

## 2. Security Strengths

### ✅ Authorization Code Flow
- Uses standard OAuth 2.0 authorization code flow
- Proper redirect URI validation
- No use of insecure implicit flow

### ✅ CSRF Protection
- State parameter generation with `secrets.token_hex(16)`
- Redis-backed state storage with 10-minute expiration
- State validation before token exchange

### ✅ Secure Browser Usage
- Uses full browser redirects (not webviews)
- Proper `Content-Security-Policy` headers
- HTTPS enforced in production

### ✅ Client Configuration
- OAuth client created manually via Google Console
- Proper redirect URI configuration
- Production mode enabled (not test mode)

### ✅ Credential Storage
- Client ID/secret stored in environment variables
- Not hardcoded in source code
- Loaded from Heroku config (encrypted at rest)

---

## 3. Compliance Checklist

| Best Practice | Status | Notes |
|--------------|--------|-------|
| Use secure OAuth flows | ✅ PASS | Authorization code flow |
| Handle client credentials securely | 🔴 FAIL | Logging credentials |
| Store credentials in secret manager | 🟡 PARTIAL | Env vars only, not Secret Manager |
| Handle user tokens securely | 🔴 FAIL | No refresh token storage |
| Encrypt tokens at rest | 🔴 FAIL | Not storing tokens |
| Use secure browsers | ✅ PASS | Full browser redirects |
| Use incremental authorization | 🔴 FAIL | All scopes requested upfront |
| Handle refresh token revocation | 🔴 FAIL | Not implemented |
| Integrate Cross-Account Protection | 🔴 FAIL | Not implemented |
| Remove unused OAuth clients | ✅ PASS | Actively managed |
| Manual client creation | ✅ PASS | Created via Console |

**Overall Compliance Score: 5/11 (45%)**

---

## 4. Immediate Action Items

### Priority 1: Critical (Within 24 hours)

1. **Remove credential logging**
   - Delete debug logging in `oauth_service.py` lines 131-140
   - Audit all log statements for sensitive data
   - Deploy immediately

2. **Rotate OAuth credentials**
   - Generate new Google OAuth client
   - Update Heroku environment variables
   - Test login flow
   - Delete old OAuth client from Google Console

### Priority 2: High (Within 1 week)

3. **Implement token storage**
   - Create `oauth_tokens` table migration
   - Add token encryption utilities
   - Store refresh tokens on successful auth
   - Test token persistence

4. **Implement scope management**
   - Reduce initial scopes to `openid` and `email`
   - Add incremental authorization for `profile`
   - Update frontend consent messaging

### Priority 3: Medium (Within 2 weeks)

5. **Implement token revocation**
   - Complete `/revoke` endpoint implementation
   - Add Google revocation API calls
   - Add cleanup procedures
   - Test revocation flow

6. **Add monitoring**
   - Track token expiration events
   - Monitor revocation events
   - Alert on unusual patterns
   - Log sanitized metadata only

### Priority 4: Low (Within 1 month)

7. **Integrate Cross-Account Protection**
   - Register for RISC events
   - Implement webhook handler
   - Test revocation notifications

8. **Migrate to Secret Manager**
   - Set up Google Cloud Secret Manager
   - Migrate OAuth credentials
   - Update deployment process
   - Document secret rotation procedure

---

## 5. Code Changes Required

### File: `app/services/oauth_service.py`

**REMOVE (lines 131-140):**
```python
# DEBUG: Log FULL token exchange payload
logger.error(
    f"[DEBUG] FULL TOKEN EXCHANGE PAYLOAD:\n"
    f"  URL: {self.token_url}\n"
    f"  client_id: {self.client_id}\n"
    f"  client_secret: {self.client_secret[:10]}...{self.client_secret[-5:]}\n"
    f"  code: {code}\n"
    f"  grant_type: authorization_code\n"
    f"  redirect_uri: {self.redirect_uri}"
)
```

**REPLACE WITH:**
```python
# Log sanitized exchange metadata
logger.info(
    f"Token exchange attempt | "
    f"provider=google "
    f"code_hash={abs(hash(code))} "
    f"client_id_prefix={self.client_id[:20]}..."
)
```

### File: `app/models/oauth_models.py` (NEW)

```python
"""OAuth token storage models."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.sql import func
from app.db.base_class import Base

class OAuthToken(Base):
    """Encrypted OAuth tokens for user accounts."""
    
    __tablename__ = "oauth_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False, index=True)
    
    # Encrypted with Fernet (symmetric encryption)
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)
    
    token_type = Column(String(50), default="bearer")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(JSON, nullable=True)  # ["openid", "email", "profile"]
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_oauth_tokens_user_provider", "user_id", "provider", unique=True),
        Index("ix_oauth_tokens_revoked", "revoked_at"),
    )
```

### File: `app/utils/token_encryption.py` (NEW)

```python
"""Token encryption utilities using Fernet."""

from cryptography.fernet import Fernet
from app.core.config import settings
import base64
import hashlib

def _get_fernet_key() -> bytes:
    """Derive Fernet key from JWT_SECRET."""
    # Use PBKDF2 to derive a proper 32-byte key
    key_material = settings.JWT_SECRET.encode()
    derived = hashlib.pbkdf2_hmac('sha256', key_material, b'oauth_salt', 100000)
    return base64.urlsafe_b64encode(derived)

def encrypt_token(token: str) -> str:
    """Encrypt OAuth token for storage."""
    fernet = Fernet(_get_fernet_key())
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str) -> str:
    """Decrypt OAuth token from storage."""
    fernet = Fernet(_get_fernet_key())
    return fernet.decrypt(encrypted.encode()).decode()
```

---

## 6. Testing Requirements

### Security Tests

- [ ] Verify no credentials in logs (grep logs for "client_secret", "GOCSPX")
- [ ] Test token encryption/decryption
- [ ] Verify tokens stored encrypted at rest
- [ ] Test token revocation cleanup
- [ ] Verify state token uniqueness
- [ ] Test CSRF protection with invalid state
- [ ] Verify redirect URI validation

### Functional Tests

- [ ] Test login with minimal scopes
- [ ] Test incremental authorization
- [ ] Test token refresh flow
- [ ] Test graceful scope denial handling
- [ ] Test token expiration handling
- [ ] Test revocation endpoint
- [ ] Test re-authentication after revocation

---

## 7. Deployment Checklist

### Pre-Deployment

- [ ] Remove debug logging from `oauth_service.py`
- [ ] Add token storage models
- [ ] Run database migration for `oauth_tokens`
- [ ] Add token encryption utilities
- [ ] Update OAuth service to store tokens
- [ ] Update tests for new functionality

### Deployment

- [ ] Deploy code changes to staging
- [ ] Test OAuth flow on staging
- [ ] Generate new OAuth client credentials
- [ ] Update Heroku config vars
- [ ] Deploy to production
- [ ] Verify production OAuth flow

### Post-Deployment

- [ ] Monitor logs for errors
- [ ] Track OAuth success/failure rates
- [ ] Verify no credential leakage
- [ ] Test token revocation
- [ ] Update security documentation
- [ ] Schedule secret rotation (quarterly)

---

## 8. Long-Term Recommendations

### Secret Management

**Current:** Environment variables on Heroku  
**Recommended:** Google Cloud Secret Manager

**Benefits:**
- Automatic secret rotation
- Access audit logs
- Version history
- Fine-grained IAM controls
- Reduced credential exposure

**Implementation:**
```python
from google.cloud import secretmanager

def get_oauth_credentials():
    """Fetch OAuth credentials from Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    
    client_id = client.access_secret_version(
        name="projects/PROJECT_ID/secrets/google-oauth-client-id/versions/latest"
    ).payload.data.decode()
    
    client_secret = client.access_secret_version(
        name="projects/PROJECT_ID/secrets/google-oauth-client-secret/versions/latest"
    ).payload.data.decode()
    
    return client_id, client_secret
```

### Monitoring & Alerting

**Metrics to Track:**
- OAuth login success rate
- Token exchange failures
- Token revocation events
- Unusual login patterns
- Scope request denials

**Alerts to Configure:**
- OAuth success rate < 95%
- Multiple token exchange failures from same IP
- Credential rotation overdue (> 90 days)
- Unusual spike in revocations

### Compliance

**Regular Audits:**
- Quarterly security reviews
- Annual penetration testing
- Bi-annual credential rotation
- Monthly log audits for sensitive data

**Documentation:**
- Keep OAuth flow diagrams updated
- Document all credential rotations
- Maintain incident response procedures
- Update privacy policy with OAuth details

---

## 9. References

- [Google OAuth 2.0 Best Practices](https://developers.google.com/identity/protocols/oauth2/production-readiness)
- [OAuth 2.0 Security Best Current Practice](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
- [OWASP OAuth Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [Cross-Account Protection (RISC)](https://developers.google.com/identity/protocols/risc)

---

## 10. Conclusion

The current OAuth implementation is **functionally correct** but has **critical security gaps** that must be addressed before production readiness:

**Critical Issues:**
1. 🔴 Credential exposure in logs
2. 🔴 No refresh token storage
3. 🔴 No token revocation handling

**Next Steps:**
1. **Immediately** remove credential logging and rotate secrets
2. **This week** implement token storage with encryption
3. **Next week** complete token revocation functionality

**Timeline to Production-Ready:** 2-3 weeks with focused effort

Once these issues are resolved, the OAuth implementation will meet Google's security standards and provide a secure, user-friendly authentication experience.

---

**Audit Performed By:** GitHub Copilot  
**Review Required By:** Senior Security Engineer  
**Next Review Date:** December 22, 2025
