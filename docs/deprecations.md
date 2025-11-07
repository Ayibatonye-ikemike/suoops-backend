# Deprecation Plan

## Legacy Authentication Endpoints (Removed)
The temporary endpoints `/auth/register` and `/auth/login` used for password-style flows have now been fully removed (replaced by OTP flows `/auth/signup/*` and `/auth/login/*`).

### Rationale for Removal
- They duplicate logic present in the OTP-based flow.
- They bypass newer security & telemetry improvements.
- They encourage password-style assumptions the product has moved away from (phone-first + OTP).

### Removal Timeline (Executed)
| Phase | Date | Action |
|-------|------|--------|
| Hard Removal | 2025-11-07 | Endpoints deleted from codebase; tests migrated to OTP signup/login. |

### Client Migration
1. Switch to `/auth/request-otp` then `/auth/verify-otp` flow.
2. Persist received token bundle exactly as before (no structural change required).
3. Ensure refresh logic uses `/auth/refresh` if implemented.

### Post-Removal Follow Ups
- (Optional) Implement 410 Gone shim if any external client traffic is later detected attempting old paths.
- Add metrics around OTP flows to ensure comparable visibility (`auth_signup_request_total`, `auth_login_verify_total`).

### Risk Mitigation
- Monitor metrics: `auth_legacy_login_requests_total`, `auth_legacy_register_requests_total`.
- Provide early warning to top users (if identifiable) via email.

## Feature Flag: Voice Invoice Gating
New flag `FEATURE_VOICE_REQUIRES_PAID` controls whether voice invoice feature requires a paid subscription in production.

### Default Behavior
- `True`: Production requires non-FREE plan; dev/test always allowed.
- `False`: All environments allow voice invoices for all users.

### Future Considerations
- Add granular plan-based usage counters.
- Potential split flag for OCR vs. voice if adoption differs.

## Follow Ups
- Add Deprecation headers implementation.
- Instrument legacy endpoint counters.
- Announce flag in ops runbook.
