# SuoOps Access Control Policy

## 1. Purpose and Scope

This Access Control Policy defines how access to SuoOps systems, applications, and data is granted, managed, and revoked to ensure security and compliance.

**Effective Date**: November 21, 2025
**Review Frequency**: Quarterly
**Policy Owner**: Security Lead

## 2. Access Control Principles

### Principle of Least Privilege
Users are granted the minimum level of access required to perform their job functions.

### Need-to-Know Basis
Access to sensitive data is restricted to those who require it for legitimate business purposes.

### Separation of Duties
Critical functions are divided among multiple individuals to prevent fraud and errors.

### Defense in Depth
Multiple layers of security controls protect systems and data.

## 3. User Access Levels

### Role-Based Access Control (RBAC)

| Role | Access Level | Permissions |
|------|-------------|-------------|
| **Customer (User)** | Standard | - Create/view own invoices<br>- Manage own profile<br>- Update payment info<br>- View own reports |
| **Staff** | Elevated | - View all invoices<br>- Assist with customer support<br>- View anonymized analytics<br>- Cannot modify invoices |
| **Admin** | Full | - All Staff permissions<br>- User management<br>- System configuration<br>- Access to audit logs<br>- Invoice modifications |
| **Developer** | Technical | - Code repository access<br>- Staging environment<br>- Read-only production logs<br>- No direct production access |
| **Super Admin** | Unrestricted | - All Admin permissions<br>- Database access<br>- Infrastructure management<br>- Security configuration<br>- Audit log access |

### Access Matrix

| Resource | Customer | Staff | Admin | Developer | Super Admin |
|----------|----------|-------|-------|-----------|-------------|
| Own invoices | Read/Write | Read | Read/Write | No Access | Read/Write |
| Others' invoices | No Access | Read | Read/Write | No Access | Read/Write |
| User profiles | Own only | Read | Read/Write | No Access | Read/Write |
| Payment data | Own only | Masked | Masked | No Access | Full |
| System config | No Access | No Access | Limited | No Access | Full |
| Database | No Access | No Access | No Access | Staging only | Full |
| Audit logs | No Access | No Access | Read | No Access | Read/Write |
| Code repository | No Access | No Access | No Access | Read/Write | Read/Write |

## 4. Account Management

### Account Creation

**New User Accounts:**
1. Automated via self-registration with OTP verification
2. Default role: Customer (User)
3. Email verification required
4. Strong password requirements enforced

**Administrative Accounts:**
1. Requires approval from Security Lead or CTO
2. Created via admin console or CLI
3. Multi-factor authentication (MFA) required
4. Access logged and monitored

**Process:**
```bash
# Create staff account (requires Super Admin)
heroku run python -c "
from app.db.session import SessionLocal
from app.models.models import User, SubscriptionPlan
from passlib.context import CryptContext

db = SessionLocal()
user = User(
    email='staff@suoops.com',
    phone='+2341234567890',
    name='Staff Member',
    plan=SubscriptionPlan.ENTERPRISE,
    role='staff',
    phone_verified=True
)
db.add(user)
db.commit()
print(f'Created staff account: {user.id}')
" --app suoops-backend
```

### Account Modification

**Role Changes:**
- Requires approval from Security Lead or higher
- Logged in audit trail
- Notification sent to user
- Reviewed quarterly

**Password Changes:**
- User-initiated: Anytime via settings
- Admin-initiated: Only via password reset link
- Force password change: After security incident

**Account Updates:**
- Users can update own profile
- Email changes require verification
- Phone changes require OTP verification

### Account Suspension/Termination

**Suspension Triggers:**
- Suspicious activity detected
- Payment disputes
- Terms of Service violation
- Security investigation
- Legal requirement

**Suspension Process:**
1. Account locked immediately
2. User notified via email
3. Incident logged
4. Investigation initiated
5. Resolution within 48 hours

**Termination Process:**
1. Account deactivated (soft delete)
2. Access revoked immediately
3. Data retained per retention policy
4. Export available upon request (GDPR)
5. Final notification sent

**Staff Offboarding:**
1. HR notifies Security Lead
2. Access revoked within 24 hours:
   ```bash
   # Disable staff account
   heroku run python -c "
   from app.db.session import SessionLocal
   from app.models.models import User
   db = SessionLocal()
   user = db.query(User).filter(User.email=='ex-staff@suoops.com').first()
   if user:
       user.role = 'user'  # Downgrade to regular user
       db.commit()
       print(f'Revoked staff access for {user.email}')
   " --app suoops-backend
   ```
3. API keys/tokens revoked
4. GitHub/repository access removed
5. Exit interview checklist completed

## 5. Authentication Requirements

### Password Policy

**Minimum Requirements:**
- Length: 8 characters minimum
- Complexity: Mix of letters, numbers
- Case sensitivity: Mixed case required
- Prohibited: Common passwords, dictionary words
- History: Cannot reuse last 3 passwords

**Implementation:**
```python
# app/core/security.py validates:
def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if password.isdigit() or password.isalpha():
        raise ValueError("Password must include both letters and numbers")
    if password.lower() == password or password.upper() == password:
        raise ValueError("Password must include mixed case characters")
```

### Multi-Factor Authentication (MFA)

**Required for:**
- Admin and Super Admin accounts
- Staff accounts with access to customer data
- API access (OAuth applications)

**Supported Methods:**
- Email OTP (6-digit code)
- WhatsApp OTP (for phone-verified accounts)
- SMS OTP (via Termii)

**MFA Bypass:**
- Not permitted for privileged accounts
- Temporary bypass requires Security Lead approval
- Limited to 24 hours maximum
- Logged and monitored

### Session Management

**Session Configuration:**
- Access token lifetime: 24 hours
- Refresh token lifetime: 14 days
- Idle timeout: 30 minutes
- Concurrent sessions: Allowed (max 3 devices)

**Session Termination:**
- User logout: Immediate token invalidation
- Password change: All sessions terminated
- Security incident: Force logout all users
- Suspicious activity: Individual session termination

## 6. Authorization Controls

### API Access Control

**JWT Token Structure:**
```json
{
  "sub": "user_id",
  "plan": "pro",
  "role": "admin",
  "iat": 1700000000,
  "exp": 1700086400
}
```

**Endpoint Protection:**
- All endpoints require authentication (except public invoice view)
- Role-based access enforced via decorators
- Rate limiting applied per plan
- API audit logging enabled

**Example Authorization Check:**
```python
from app.api.routes_auth import get_current_user_id, require_role

@router.post("/admin/users")
@require_role("admin")  # Requires admin role
async def create_user(current_user_id: CurrentUserDep):
    # Only accessible by admins
    pass
```

### Database Access Control

**Application-Level:**
- SQLAlchemy ORM with parameterized queries
- Row-level security via issuer_id filtering
- Connection pooling (10 connections max)
- Read replicas for analytics (future)

**Database-Level:**
- Heroku Postgres with SSL required
- Role: Application user (limited permissions)
- No direct console access in production
- Backup access: Separate read-only role

**Sensitive Data:**
- Passwords: bcrypt hashed (12 rounds)
- API keys: Environment variables only
- Payment data: PCI compliance (via Paystack)
- Email: Optional encryption (Fernet)

## 7. Third-Party Access

### API Integrations

**Current Integrations:**
- Paystack (payment processing)
- Brevo (email delivery)
- AWS S3 (file storage)
- Heroku (infrastructure)
- Sentry (error tracking)

**Access Control:**
- API keys rotated every 90 days
- Minimum required permissions
- Activity monitored via logs
- Vendor security reviews annually

**API Key Storage:**
```bash
# All keys stored in Heroku config vars
heroku config --app suoops-backend

# Never in code or .env files
# Rotated quarterly or immediately if compromised
```

### External Auditors

**Access Granted:**
- Read-only database snapshots (no production access)
- Anonymized logs and metrics
- Documentation and policies
- Code repository (read-only)

**Requirements:**
- NDA signed before access
- Time-limited access (audit period only)
- All activity logged
- Exit report required

## 8. Privileged Access Management

### Super Admin Access

**Granted To:**
- CTO
- Lead Engineer
- Security Lead (max 3 people)

**Requirements:**
- MFA mandatory
- Strong password (16+ characters)
- Access logged and reviewed weekly
- Emergency access procedures documented

**Emergency Access:**
```bash
# Break-glass account (use only in emergency)
# Requires Security Lead approval
# Logged and reviewed within 24 hours

heroku run bash --app suoops-backend
# Document reason and actions taken
```

### Database Console Access

**Production Database:**
- Restricted to emergency use only
- Requires approval from 2 people
- All queries logged
- Read-only preferred (unless critical fix)

**Access Process:**
1. Submit access request with justification
2. Approval from Security Lead + CTO
3. Access granted for specific timeframe (max 4 hours)
4. All actions logged and reviewed
5. Access automatically revoked after timeframe

**Command:**
```bash
# Production database console (use with extreme caution)
heroku pg:psql --app suoops-backend

# All queries logged to audit trail
# Prefer read-only queries
```

## 9. Access Reviews

### Quarterly Access Review

**Process:**
1. Generate access report for all users
2. Review with department heads
3. Verify role assignments are appropriate
4. Remove unnecessary privileges
5. Document review findings

**Checklist:**
- [ ] Active users match current staff roster
- [ ] Role assignments align with job functions
- [ ] No orphaned accounts (terminated employees)
- [ ] MFA enabled for privileged accounts
- [ ] API keys rotated within policy
- [ ] Third-party access still required

### Automated Monitoring

**Daily:**
- Failed login attempts (threshold: 5/hour)
- Unusual access patterns
- Privileged actions (admin operations)
- API key usage

**Weekly:**
- Access anomaly report
- Dormant account review
- Permission changes audit
- Third-party integration health

**Monthly:**
- User access summary
- Role distribution analysis
- MFA compliance check
- Password age report

## 10. Logging and Auditing

### Access Logs

**What is Logged:**
- Authentication attempts (success/failure)
- Authorization decisions (allowed/denied)
- Privileged actions (admin operations)
- Data access (invoice views, user profile changes)
- Session creation/termination
- API key usage

**Log Retention:**
- Access logs: 90 days in hot storage
- Audit logs: 1 year in warm storage
- Security events: 7 years in cold storage
- Compliance logs: Per regulatory requirements

**Log Format:**
```json
{
  "timestamp": "2025-11-21T10:30:00Z",
  "event": "authentication",
  "action": "login_success",
  "user_id": 12345,
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "role": "admin"
}
```

### Audit Trail

**Accessible To:**
- Super Admin: Full access
- Security Lead: Full access
- Compliance Officer: Read-only
- External Auditors: Time-limited, specific queries

**Cannot Be:**
- Modified by anyone
- Deleted (except per retention policy)
- Disabled without Security Lead approval

## 11. Physical Access (for Office/Data Center)

**Note**: SuoOps is cloud-based (Heroku), physical access to servers is managed by Heroku's security policies.

**Office Access:**
- Badge-controlled entry
- Visitor log maintained
- Escort required for visitors
- Screen lock policy (< 5 minutes idle)
- Clean desk policy

## 12. Compliance and Exceptions

### Regulatory Compliance

**NDPA (Nigeria Data Protection Act):**
- Data subject access rights
- Consent management
- Data minimization
- Breach notification (72 hours)

**PCI DSS (via Paystack):**
- No storage of card data
- Payment handled by certified processor
- PCI compliance inherited

### Policy Exceptions

**Request Process:**
1. Submit exception request with business justification
2. Security risk assessment
3. Approval from Security Lead + Department Head
4. Time-limited (max 90 days)
5. Compensating controls implemented
6. Documented and reviewed monthly

**Approval Levels:**
| Risk Level | Approver |
|------------|----------|
| Low | Security Lead |
| Medium | Security Lead + CTO |
| High | Security Lead + CTO + CEO |

## 13. Violations and Enforcement

### Policy Violations

**Examples:**
- Sharing credentials
- Unauthorized access attempts
- Bypassing access controls
- Failure to report security incidents

**Consequences:**
- First violation: Written warning + retraining
- Second violation: Access suspension + review
- Third violation: Termination
- Criminal activity: Law enforcement referral

### Reporting

**Report Security Concerns:**
- Email: security@suoops.com
- Slack: #security-incidents (for staff)
- Anonymous: [Whistleblower hotline]

## 14. Training and Awareness

### Required Training

**All Users:**
- Security awareness training (annually)
- Password security best practices
- Phishing awareness

**Staff and Admins:**
- Access control policy (upon hire)
- Data handling procedures
- Incident reporting
- Quarterly security updates

**Developers:**
- Secure coding practices
- OWASP Top 10
- Security testing
- Access control implementation

## 15. Policy Review and Updates

**Review Triggers:**
- Quarterly scheduled review
- After security incidents
- Regulatory changes
- System architecture changes
- Organizational changes

**Update Process:**
1. Draft policy changes
2. Review with Security Lead
3. Approval from CTO
4. Communication to all staff
5. Training on changes (if significant)
6. Version control and archiving

---

**Document Control**
- Version: 1.0
- Effective Date: November 21, 2025
- Next Review: February 21, 2026
- Policy Owner: Security Lead
- Approved By: CTO, CEO

**Revision History**
| Version | Date | Changes | Approved By |
|---------|------|---------|-------------|
| 1.0 | 2025-11-21 | Initial policy creation | CTO |
