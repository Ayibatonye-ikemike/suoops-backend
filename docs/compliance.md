# Compliance & Privacy Overview

This document summarizes baseline compliance posture and actions for Suoops with respect to data privacy, protection, and regional regulations.

## Regulatory Targets
- GDPR (EU personal data handling)
- NDPR (Nigeria Data Protection Regulation)
- CAN-SPAM (email sending compliance)
- Potential SOC 2 (future) – security, availability, confidentiality

## Data Inventory
| Category | Examples | Location | Protection |
|----------|----------|----------|------------|
| PII | Names, emails | PostgreSQL | At-rest encryption (cloud provider disk); consider column-level encryption later |
| Auth | Password hashes, OAuth tokens | PostgreSQL | Hash (bcrypt/argon2), tokens encrypted or short-lived |
| Usage | Logs, metrics | Sentry, log store | Pseudonymized where possible |
| Assets | Uploaded documents | S3 | SSE-KMS, access scoped via IAM |

## Principles
1. Data Minimization – Only store fields required for business logic.
2. Purpose Limitation – Document each data field’s purpose in `docs/data-dictionary.md` (to be created).
3. Defense in Depth – Combine app security headers, WAF, RBAC, rate limits.
4. Least Privilege – RBAC for admin/staff functions; restrict direct DB access.
5. Auditability – Introduce audit logging (planned) for sensitive operations.

## User Rights (GDPR/NDPR)
- Right of Access: Provide export (JSON) via authenticated endpoint within 30 days.
- Right to Rectification: Allow profile edits; maintain change history for 90 days.
- Right to Erasure: Implement queued deletion job removing user rows and associated S3 objects.
- Right to Data Portability: Same export endpoint fulfills portability.
- Right to Restrict Processing: Flag user record; suppress marketing emails.

## Consent & Email
- Store marketing consent boolean with timestamp.
- Unsubscribe link in all outbound marketing emails.
- Suppress sends for users who withdrew consent within 24h.

## Cookies & Tracking
- Minimal cookies: session, CSRF token.
- Avoid third-party analytics until cookie policy published.
- Draft `cookie-policy.md` and link from footer.

## Data Retention
| Data | Retention | Disposal Method |
|------|-----------|-----------------|
| Inactive user accounts | 24 months | Delete + purge backups (script) |
| Auth logs | 90 days | Secure delete (object lifecycle) |
| Email events | 12 months | Aggregate stats retained, raw events purged |
| Backups | 14 days (DB), objects per lifecycle | Automatic expiry |

## Security Controls Mapping
| Control | Status | Notes |
|---------|--------|-------|
| Encrypted transport (TLS) | Implemented | All endpoints via HTTPS |
| Secrets management | Partially | Hardening done; secret scanning workflow added |
| RBAC | Partial | Admin route only; expand coverage |
| Central logging | Partial | Sentry; need audit log channel |
| Backups | Draft | Strategy documented; script pending |
| WAF | Planned | Guidance documented |
| Vulnerability scanning | Partial | Add dependency scan CI (pip-audit) |

## Incident Response (High-Level)
1. Detect via monitoring/alerts.
2. Classify severity (data leak vs availability).
3. Contain: revoke exposed credentials, isolate affected services.
4. Eradicate: patch vulnerability, rotate secrets.
5. Recover: restore from clean backup if data corruption.
6. Postmortem: document timeline, impacted data, remediation steps.
7. Notify users/regulators within statutory windows (GDPR: 72h for certain breaches).

## Roadmap Items
- Implement audit logging module with immutable append-only store.
- Create data dictionary & classification mapping.
- Add automated DSAR (Data Subject Access Request) workflow.
- Integrate pip-audit and CodeQL scanning in CI.
- Encrypt selected PII columns with application-managed keys (phase 2).

## References
- GDPR text: https://gdpr.eu/
- NDPR: Nigeria Data Protection Regulation
- OWASP ASVS for application security maturity

---
Owned by: Platform Engineering / Compliance
Review Cycle: Quarterly
Last Updated: YYYY-MM-DD