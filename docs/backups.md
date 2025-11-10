# Backup & Recovery Strategy

This document defines the backup, retention, encryption, and recovery procedures for the Suoops platform.

## Objectives
- Guarantee restorable copies of all critical data (PostgreSQL, Redis ephemeral state, S3 assets) within acceptable RPO/RTO.
- Provide auditable, automated, and encrypted backups.
- Minimize data loss to < 15 minutes for the primary database (target RPO).
- Restore service within 60 minutes from latest consistent snapshot (target RTO).

## Scope
1. PostgreSQL primary database.
2. S3 object storage (user uploads, generated documents).
3. Redis: Only persistent data (if any). Generally treated as cache; not backed up except for durable queues (evaluate if using Redis persistence for Celery or rate limit counters).

## Data Classification
- PII: User profile data, email addresses, invoices.
- Confidential: API keys, OAuth tokens (never stored in plaintext backups; stored only in DB encrypted columns / not exported separately).
- Operational Metrics: Non-sensitive, may be excluded from long-term retention.

## PostgreSQL Backups
| Type | Frequency | Retention | Tool |
|------|-----------|-----------|------|
| Full logical dump (pg_dump) | Daily (02:00 UTC) | 14 days | pg_dump + gzip |
| WAL archiving / incremental (optional) | Every 5 min | 24 hours | WAL-E / pgBackRest |

### Automation Script (example)
Stored at `scripts/backup/pg_dump_to_s3.sh` (to be created) and run via Cron or GitHub Actions self-hosted runner.

#### Sample Script
```bash
#!/usr/bin/env bash
set -euo pipefail

TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DB_URL="${DATABASE_URL}" # e.g. postgresql://user:pass@host:5432/db
S3_BUCKET="s3://suoops-backups/postgres"
TMP_DUMP="/tmp/pg_${TIMESTAMP}.sql.gz"

echo "[+] Starting pg_dump ${TIMESTAMP}" >&2
pg_dump --no-owner --no-privileges "$DB_URL" | gzip -9 > "$TMP_DUMP"

echo "[+] Uploading to S3" >&2
aws s3 cp "$TMP_DUMP" "$S3_BUCKET/$TIMESTAMP.sql.gz" --sse AES256

echo "[+] Verifying upload" >&2
aws s3 ls "$S3_BUCKET/$TIMESTAMP.sql.gz" || { echo "Upload failed"; exit 1; }

rm "$TMP_DUMP"
echo "[+] Done"
```

### Encryption
- Use S3 Server-Side Encryption (SSE-S3 or SSE-KMS).
- Optionally layer client-side encryption using `age` or `openssl` before upload.

### Access Control
- Restrict S3 bucket with IAM policy: only backup role can write; restore role can read.
- Enable bucket versioning & MFA delete for high-assurance environments.

## S3 Object Backups
Because S3 already provides durability (11 9's), focus on lifecycle + replication:
- Enable Cross-Region Replication (CRR) for disaster recovery (optional phase 2).
- Lifecycle rules:
  - Transition to STANDARD_IA after 30 days.
  - Transition to GLACIER after 180 days.
  - Expire non-critical objects after 1 year.

## Redis Strategy
- Treat as non-persistent cache (no backup) unless queues/state require persistence.
- If persistence required: enable AOF every second and snapshot (RDB) every 6 hours; copy RDB to S3 with same script pattern.

## Verification
- Monthly restore test to staging: provision blank DB, download latest dump, apply migrations, run smoke tests.
- Maintain a checklist (`docs/backup-restore-test-log.md`) documenting date, operator, success/failure, time to restore.

## Monitoring & Alerts
- Emit metric/Slack webhook on backup success/failure.
- Alert if latest backup age > 26 hours.

## Disaster Recovery Procedure
1. Declare incident; freeze writes.
2. Provision new DB instance.
3. Restore last full dump.
4. (If WAL incremental enabled) replay WAL segments to point-in-time.
5. Run migrations (idempotent).
6. Reconfigure application DATABASE_URL.
7. Run smoke tests (auth, invoice creation, OCR, email send).
8. Lift write freeze.

## Privacy & Compliance Notes
- Ensure backups containing PII are encrypted at rest and in transit.
- Honor data deletion requests: implement periodic purge job to remove user-specific rows from historical dumps (or switch to column-level encryption so deleted user data is unrecoverable without key).

## Future Enhancements
- Adopt physical backups (pgBackRest) for faster restore time.
- Enable PITR via WAL archiving.
- Add backup integrity hash (SHA256) stored separately.
- Implement automated restore validation pipeline.

## Quick Commands (Reference)
```bash
# Manual adhoc backup
pg_dump "$DATABASE_URL" | gzip -9 > backup.sql.gz

# List S3 backups
aws s3 ls s3://suoops-backups/postgres/

# Restore
gunzip -c backup.sql.gz | psql "$DATABASE_URL"
```

---
Owned by: Platform Engineering
Review Cycle: Quarterly
Last Updated: YYYY-MM-DD