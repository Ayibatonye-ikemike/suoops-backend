# WAF Change Log

Records all modifications to WAF rules for traceability.

| Date | Operator | Environment | Rule ID/Name | Action | Mode (LOG/BLOCK) | Reason | Notes |
|------|----------|-------------|--------------|--------|------------------|--------|-------|
| YYYY-MM-DD | user@example.com | prod | cloudflare:managed-owasp | enable | BLOCK | Baseline protection | Initial deployment |
| YYYY-MM-DD | user@example.com | prod | aws:SQLi | enable | BLOCK | Detect SQL injection | Added after false-positive review |
| YYYY-MM-DD | user@example.com | staging | custom:login-bruteforce | add | LOG | Monitor brute force | Evaluating thresholds |

## Process
1. Propose rule change via ticket (include expected impact).
2. Deploy to staging in LOG mode for 24h.
3. Review metrics (false positives, hits).
4. Promote to prod; update table.
5. For removals: record prior state and rationale.

## Emergency Changes
If a rule causes outages (legitimate traffic blocked), switch to LOG mode and record entry with reason "service impairment".

---
Owned by: Platform Engineering
Review Cycle: Quarterly
Last Updated: YYYY-MM-DD