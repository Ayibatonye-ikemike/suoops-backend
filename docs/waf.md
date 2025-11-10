# Web Application Firewall (WAF) Guidance

This document outlines recommended WAF deployment patterns and baseline rules for Suoops.

## Goals
- Mitigate common web attacks (OWASP Top 10, bots, credential stuffing).
- Provide defense-in-depth alongside application-level security headers and rate limiting.
- Preserve low false-positive rate and observable metrics for tuning.

## Deployment Options
| Option | Pros | Cons | Recommended Use |
|--------|------|------|-----------------|
| Cloudflare WAF | Easy setup, managed rules, bot mgmt | Paid tiers for advanced features | Default for custom domain |
| AWS WAF (ALB / CloudFront) | Tight AWS integration, fine-grained rules | More operational overhead | If infra already on AWS ALB/CloudFront |
| Fastly Edge Security | High performance, advanced features | Cost | High traffic enterprise phase |

## Baseline Rule Set
1. Managed OWASP ruleset (Cloudflare: OWASP, AWS: AWSManagedRulesCommonRuleSet).
2. SQL injection detection.
3. XSS detection.
4. Directory traversal patterns.
5. Anonymous IP / known bot lists (enable challenge not block initially).
6. Rate limiting (app already enforces; ensure WAF doesn't conflict).
7. Block POST bodies > 5MB (align with RequestSizeLimitMiddleware).
8. Challenge high-risk countries (if geo-risk emerges; log-only first).

## Custom Rules (Phase 2)
- Block requests missing required headers (e.g. `Host`, `User-Agent`).
- Enforce allowed HTTP methods: GET, POST, PUT, PATCH, DELETE; block TRACE/OPTIONS (except CORS preflight OPTIONS).
- Match and block obvious credential stuffing patterns (rapid login failures from single IP).
- Throttle 429 repeat offenders (combine with fail2ban style list).

## Exclusions & Tuning
- Exclude health check endpoints (`/health`, `/metrics`) from strict anomaly detection.
- Exclude static asset paths from bot challenges.
- Maintain an allowlist for approved API integrators by IP or token.

## Logging & Monitoring
- Centralize WAF logs (Cloudflare logs to R2 / AWS WAF logs to CloudWatch + Kinesis).
- Daily review of top blocked rule IDs.
- Alert on sudden spike (>300% hour-over-hour) in blocked requests.

## Change Management
- All rule changes require ticket + peer review.
- Deploy new rules in COUNT/LOG mode for 24h before BLOCK.
- Maintain `docs/waf-change-log.md` with date, rule, action, operator, result.

## Emergency Bypass
- Have runbook to temporarily disable aggressive custom rule IDs if causing outage.
- Never disable full managed ruleset; prefer narrowing scope or adding targeted allowlist.

## Privacy & Compliance
- Ensure bot management challenges don't collect excessive personal data.
- Log retention: rotate WAF logs every 30 days (export metrics only).

## Future Enhancements
- Automated anomaly detection feed into Slack (sudden geo-shift, unusual method usage).
- ML-based bot scoring (Cloudflare Bot Management / AWS Advanced Shield).
- Integrate with SIEM (ruleset events tagged with application correlation IDs when feasible).

---
Owned by: Platform Engineering
Review Cycle: Quarterly
Last Updated: YYYY-MM-DD