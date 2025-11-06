# NRS Registration Checklist

**Platform:** SuoOps E-Invoicing & Tax Compliance  
**Updated:** January 2026  
**Status:** Ready for Registration

---

## 1. TECHNICAL CAPABILITIES ✅

### API Documentation
- ✅ **URL:** https://ayibatonye-ikemike.github.io/suoops-backend/
- ✅ **Interactive Docs:** https://api.suoops.com/docs (Swagger UI)
- ✅ **Alternative Docs:** https://api.suoops.com/redoc (ReDoc)
- ✅ **Format:** OpenAPI 3.0 specification
- ✅ **Contact:** info@suoops.com, support@suoops.com, +234 816 208 8344

### Service Level Agreement (SLA)
- ✅ **URL:** https://ayibatonye-ikemike.github.io/suoops-backend/sla.html
- ✅ **Uptime Guarantee:** 99.9% (43.2 minutes max downtime/month)
- ✅ **Support Hours:** Mon-Fri 9AM-6PM WAT
- ✅ **Emergency Support:** 24/7 for P1 incidents
- ✅ **Response Times:**
  - P1 (Critical): 30 minutes
  - P2 (High): 2 hours
  - P3 (Medium): 8 hours
  - P4 (Low): 24 hours

### Production URLs
- ✅ **API Endpoint:** https://api.suoops.com
- ✅ **Frontend Dashboard:** https://app.suoops.com
- ✅ **Status Page:** https://status.suoops.com
- ✅ **Health Check:** https://api.suoops.com/healthz
- ✅ **SSL Certificate:** Valid until January 26, 2026 (ACM)

---

## 2. DATA AND INFORMATION SECURITY ✅

### Nigerian Data Protection Act (NDPA) Compliance
- ✅ **Status:** COMPLIANT
- ✅ **Documentation:** SECURITY-COMPLIANCE.md
- ✅ **Implementation:**
  - Data minimization (only necessary business/tax data)
  - Explicit user consent for data processing
  - Data subject rights (access, modify, delete)
  - 72-hour breach notification protocol
  - Data Protection Officer: support@suoops.com
  - Cross-border data transfer compliance (AWS eu-north-1, GDPR)
  - 7-year audit trail for tax compliance

### Data Encryption Standards
- ✅ **At Rest:** AES-256
  - PostgreSQL database (Heroku managed encryption)
  - AWS S3 file storage (SSE-S3)
  - Bcrypt password hashing (adaptive cost)
- ✅ **In Transit:** TLS 1.3
  - HSTS enabled (31,536,000 seconds / 1 year)
  - Perfect Forward Secrecy
  - ACM certificate (auto-renewal)
- ✅ **API Security:**
  - JWT tokens (HS256 algorithm)
  - Access tokens: 24-hour expiry
  - Refresh tokens: 14-day expiry

---

## 3. AUTHENTICATION PROTOCOLS ✅

### Multi-Factor Authentication (MFA)
- ✅ **Status:** IMPLEMENTED
- ✅ **Method:** WhatsApp OTP
- ✅ **Implementation:**
  - Meta Business API integration
  - 10-minute OTP expiry
  - Rate limiting (5 attempts per 15 minutes)
- ✅ **Password Requirements:**
  - Minimum 8 characters
  - Mixed case (upper + lowercase)
  - Alphanumeric
  - Strength validation on registration

### Single Sign-On (SSO)
- ✅ **Status:** IMPLEMENTED (Code complete, pending deployment)
- ✅ **Protocol:** OAuth 2.0 with OpenID Connect (RFC 6749)
- ✅ **Provider:** Google (extensible for Microsoft, Apple)
- ✅ **Implementation Files:**
  - Service layer: `app/services/oauth_service.py` (390 lines)
  - HTTP layer: `app/api/routes_oauth.py` (230 lines)
  - Configuration: `app/core/config.py`
  - Schemas: `app/models/schemas.py`
- ✅ **Security Features:**
  - CSRF state token validation
  - One-time use validation
  - Cryptographically secure random generation
  - JWT access tokens (24-hour expiry)
  - JWT refresh tokens (14-day expiry)
- ✅ **User Provisioning:** Auto-create users, update existing
- ✅ **Scopes:** openid, email, profile
- ✅ **Documentation:** docs/oauth-setup-guide.md
- 📅 **Deployment:** Pending Google OAuth credentials + Heroku config

---

## 4. PENETRATION TESTING & VULNERABILITY ASSESSMENT

### VAPT Report Status
- ⚠️ **Status:** SCHEDULED for Q1 2026
- ⚠️ **Reason:** Awaiting final OAuth deployment before comprehensive assessment
- ⚠️ **Timeline:** Before NRS production launch (Q1 2026)
- ⚠️ **Budget:** ₦500,000 - ₦1,000,000
- ⚠️ **Vendor:** Nigerian-certified cybersecurity firm (TBD)

### Current Security Measures
- ✅ **Automated Scanning:** GitHub Dependabot enabled
- ✅ **Code Security:**
  - Input validation on all endpoints
  - SQL injection prevention (SQLAlchemy ORM)
  - XSS prevention (Content Security Policy)
  - CSRF protection (token validation)
  - Rate limiting (100 requests/minute per user)
- ✅ **Infrastructure Security:**
  - Heroku (ISO 27001, SOC 2, PCI DSS Level 1)
  - AWS S3 (ISO 27001, SOC 2/3, GDPR)
  - Vercel (SOC 2 Type II)

### Remediation Plan
1. Complete OAuth deployment (immediate)
2. Schedule VAPT with certified firm (January 2026)
3. Address findings (February 2026)
4. Submit final report to NRS (March 2026)

---

## 5. ISO 27001 COMPLIANCE

### Certification Status
- ⚠️ **Company Status:** NOT CERTIFIED (Infrastructure providers ARE certified)
- ✅ **Infrastructure Providers:**
  - Heroku: ISO 27001:2013 certified
  - AWS: ISO 27001:2013 certified
  - Vercel: SOC 2 Type II compliant
  - Paystack: PCI DSS Level 1

### ISO 27001 Alignment
We implement ISO 27001 controls:
- ✅ **A.9 Access Control:** JWT authentication, RBAC
- ✅ **A.10 Cryptography:** TLS 1.3, AES-256, bcrypt
- ✅ **A.12 Operations Security:** Logging, monitoring, backup
- ✅ **A.13 Communications Security:** HTTPS-only, HSTS, CSP
- ✅ **A.14 System Acquisition:** Secure SDLC, code review
- ✅ **A.17 Business Continuity:** 30-day backups, 99.9% SLA

### Path to Certification
- 📅 **Timeline:** 12-18 months (Q4 2026 target)
- 💰 **Cost:** ₦5,000,000 - ₦10,000,000
- 🎯 **Trigger:** Business scale > ₦100M revenue

---

## 6. COMPLIANCE GAPS SUMMARY

| Requirement | Status | Action Required | Timeline |
|------------|--------|-----------------|----------|
| NDPA Compliance | ✅ COMPLIANT | None | - |
| Data Encryption | ✅ COMPLIANT | None | - |
| MFA Support | ✅ IMPLEMENTED | None | - |
### ✅ SSO Support | SSO Support | ✅ IMPLEMENTED (Code complete, pending deployment) | MEDIUM | Deployed Q1 2026 | ₦0 (completed) |
| VAPT Report | ❌ PENDING | HIGH | Q1 2026 | ₦750K |
| ISO 27001 Cert | ❌ NOT CERTIFIED | LOW | Q4 2026 | ₦7.5M |

**UPDATE (November 7, 2025):**
- ✅ Backend OAuth deployed: Heroku v110
- ✅ Frontend OAuth deployed: Vercel production
- ✅ Google OAuth credentials configured
- ⏳ Pending: Update Google OAuth redirect URIs
- ⏳ Pending: End-to-end testing

---

## 7. DEPLOYMENT STEPS FOR SSO (IMMEDIATE)

### Step 1: Create Google OAuth App
1. Go to https://console.cloud.google.com/
2. Create project: `suopay-oauth`
3. Enable Google+ API
4. Create OAuth 2.0 credentials (Web application)
5. Add redirect URI: `https://api.suoops.com/auth/oauth/google/callback`
6. Copy Client ID and Client Secret

### Step 2: Configure Heroku Environment Variables
```bash
heroku config:set GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com" --app suoops-backend
heroku config:set GOOGLE_CLIENT_SECRET="GOCSPX-xxx" --app suoops-backend
heroku config:set OAUTH_STATE_SECRET="$(openssl rand -hex 32)" --app suoops-backend
```

### Step 3: Install authlib Dependency
Add to Heroku buildpack or requirements.txt:
```bash
# Add to requirements.txt or ensure pyproject.toml is used
authlib==1.3.0
```

### Step 4: Deploy to Production
```bash
git push heroku main
```

### Step 5: Test OAuth Flow
```bash
# Test providers endpoint
curl https://api.suoops.com/auth/oauth/providers

# Test OAuth login (in browser)
open https://api.suoops.com/auth/oauth/google/login
```

### Step 6: Update NRS Registration Form
- SSO Compatibility: **YES ✅**
- Provider: **Google OAuth 2.0 (OpenID Connect)**
- Documentation: https://ayibatonye-ikemike.github.io/suoops-backend/
- Setup Guide: docs/oauth-setup-guide.md

---

## 8. NRS REGISTRATION FORM ANSWERS

### Section A: Company Information
- **Company Name:** SuoOps Limited
- **Email:** info@suoops.com
- **Support Email:** support@suoops.com
- **Phone:** +234 816 208 8344
- **Website:** https://api.suoops.com

### Section B: Technical Capabilities
- **API Documentation:** https://ayibatonye-ikemike.github.io/suoops-backend/
- **SLA Document:** https://ayibatonye-ikemike.github.io/suoops-backend/sla.html
- **Production API:** https://api.suoops.com
- **Uptime SLA:** 99.9%
- **Support Hours:** Mon-Fri 9AM-6PM WAT, 24/7 for emergencies

### Section C: Security Compliance
- **NDPA Compliant:** YES ✅
- **Data Encryption at Rest:** YES ✅ (AES-256)
- **Data Encryption in Transit:** YES ✅ (TLS 1.3)
- **TLS Version:** 1.3 with HSTS
- **MFA Support:** YES ✅ (WhatsApp OTP)
- **SSO Support:** YES ✅ (Google OAuth 2.0 - code complete, pending deployment)
- **Password Requirements:** Minimum 8 chars, mixed case, alphanumeric
- **Session Management:** JWT tokens (24hr access, 14-day refresh)

### Section D: Vulnerability Assessment
- **VAPT Status:** SCHEDULED for Q1 2026
- **Reason for Delay:** Awaiting final OAuth deployment
- **Planned Date:** January-February 2026
- **Budget:** ₦750,000
- **Current Security:** GitHub Dependabot, automated scanning, infrastructure on ISO 27001 certified platforms

### Section E: ISO 27001
- **Company Certified:** NO (Infrastructure providers ARE certified)
- **Infrastructure Providers:** Heroku (ISO 27001:2013), AWS (ISO 27001:2013), Vercel (SOC 2 Type II)
- **ISO Controls Implemented:** A.9, A.10, A.12, A.13, A.14, A.17 (see SECURITY-COMPLIANCE.md)
- **Certification Timeline:** Q4 2026 (12-18 months)
- **Current Alignment:** HIGH (built on certified infrastructure)

---

## 9. SUPPORTING DOCUMENTATION

### Available Documents
1. ✅ **API Documentation:** https://ayibatonye-ikemike.github.io/suoops-backend/
2. ✅ **SLA Document:** https://ayibatonye-ikemike.github.io/suoops-backend/sla.html
3. ✅ **Security Compliance Report:** SECURITY-COMPLIANCE.md (in repository)
4. ✅ **OAuth Setup Guide:** docs/oauth-setup-guide.md
5. ✅ **OpenAPI Specification:** frontend/openapi.json
6. ⏳ **VAPT Report:** Scheduled Q1 2026
7. ⏳ **ISO 27001 Certificate:** Planned Q4 2026

### Document Access
All documentation is publicly accessible:
- GitHub Repository: https://github.com/Ayibatonye-ikemike/suoops-backend
- GitHub Pages: https://ayibatonye-ikemike.github.io/suoops-backend/
- Production API: https://api.suoops.com/docs

---

## 10. READINESS ASSESSMENT

### ✅ READY FOR REGISTRATION
- [x] NDPA compliance documented
- [x] Encryption standards met (AES-256, TLS 1.3)
- [x] MFA implemented (WhatsApp OTP)
- [x] SSO implemented (OAuth 2.0 - code complete)
- [x] API documentation published
- [x] SLA document published
- [x] Production environment live
- [x] SSL certificate valid
- [x] 99.9% uptime SLA

### ⏳ PENDING BEFORE PRODUCTION LAUNCH
- [ ] Deploy OAuth to production (immediate)
- [ ] Complete VAPT assessment (Q1 2026)
- [ ] Address VAPT findings (Q1 2026)

### 📋 LONG-TERM ENHANCEMENTS
- [ ] ISO 27001 certification (Q4 2026)
- [ ] Migrate OAuth state to Redis
- [ ] Add Microsoft/Apple OAuth providers
- [ ] Advanced threat protection (WAF, IDS/IPS)

---

## 11. SUBMISSION CHECKLIST

Before submitting NRS registration:
- [x] Complete all sections of registration form
- [x] Attach API documentation URL
- [x] Attach SLA document URL
- [x] Attach security compliance document
- [ ] Complete OAuth deployment
- [x] Verify all production URLs are accessible
- [ ] Schedule VAPT assessment
- [x] Designate Data Protection Officer (support@suoops.com)
- [x] Prepare incident response contact (info@suoops.com, +234 816 208 8344)

---

## 12. POST-REGISTRATION ACTION ITEMS

### Immediate (Week 1)
1. Deploy OAuth to production
2. Test OAuth flow end-to-end
3. Monitor for security incidents

### Short-term (Month 1)
1. Engage VAPT vendor
2. Begin VAPT assessment
3. Frontend OAuth integration

### Medium-term (Q1 2026)
1. Complete VAPT assessment
2. Remediate VAPT findings
3. Submit updated security documentation to NRS

### Long-term (2026)
1. Begin ISO 27001 certification process
2. Expand SSO providers (Microsoft, Apple)
3. Advanced security enhancements

---

## CONTACT INFORMATION

**General Inquiries:**  
Email: info@suoops.com  
Phone: +234 816 208 8344

**Technical Support:**  
Email: support@suoops.com  
Hours: Mon-Fri 9AM-6PM WAT  
Emergency: 24/7 for P1 incidents

**Data Protection Officer:**  
Email: support@suoops.com

---

**Prepared by:** SuoOps Technical Team  
**Last Updated:** January 2026  
**Status:** READY FOR NRS REGISTRATION ✅

