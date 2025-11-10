# Audit Log Shipping

Defines process for exporting `storage/audit.log` to external storage for retention and analysis.

## Objectives
- Preserve security-relevant events beyond local disk lifespan.
- Enable centralized querying (security reviews, incident response).
- Maintain integrity (optional hash) and restricted access.

## Scope
- File: `storage/audit.log` (JSON lines, one event per line).
- Frequency: Daily (midnight UTC) or size-trigger (>10MB) whichever comes first.

## Shipping Methods
| Method | Pros | Cons | Recommended |
|--------|------|------|------------|
| S3 upload (script + cron) | Simple, cheap | Needs rotation script | Initial phase |
| Log aggregation SaaS (Datadog/Splunk) | Powerful querying | Cost | Phase 2 |
| Self-hosted Loki | Flexible | Ops overhead | If existing stack |

## Script Example
Located at `scripts/audit/upload_audit_log_to_s3.sh` (to be created) to:
1. Stop writes (optional lock) – pilot skips.
2. Copy file to temp path.
3. Gzip & compute SHA256.
4. Upload to S3 with SSE.
5. Append metadata (hash, timestamp).
6. Truncate original file.

## IAM Policy (Simplified)
Allow: `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on `suoops-audit-logs/*` for audit role.
Separate read-only role for security analysts.

## Retention
- 12 months in S3 STANDARD.
- Transition to GLACIER after 12 months (Lifecycle rule).
- Delete after 24 months (policy + lifecycle).

## Integrity
- Store SHA256 hash in object metadata (`x-amz-meta-sha256`).
- Optional secondary record in DynamoDB (object key + hash + timestamp) for tamper evidence.

## Access Control
- Bucket private; block public ACLs and policies.
- Enforce MFA delete for critical buckets (optional).

## Alerting
- Alert if no upload in >26h.
- Alert if script exits non-zero.

## Future Enhancements
- Add compression ratio metrics.
- Ship to SIEM with enrichment (geo, role type).
- Implement per-tenant segregation if multi-tenant.

---
Owned by: Platform Engineering / Security
Review Cycle: Quarterly
Last Updated: YYYY-MM-DD