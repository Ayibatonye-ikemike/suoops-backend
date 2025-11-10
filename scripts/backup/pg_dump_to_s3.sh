#!/usr/bin/env bash
# Postgres logical backup to S3 with encryption and retention tagging.
# Requirements: aws cli configured with role granting PutObject to backup bucket; pg_dump installed.
# Usage: ./scripts/backup/pg_dump_to_s3.sh

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set (e.g. postgresql://user:pass@host:5432/db)}"
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET must be set (e.g. suoops-backups)}"

TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DAY="$(date -u +%Y-%m-%d)"
DUMP_FILE="/tmp/pg_${TIMESTAMP}.sql.gz"
S3_PATH="s3://${BACKUP_S3_BUCKET}/postgres/${DAY}/pg_${TIMESTAMP}.sql.gz"

echo "[+] Starting pg_dump at ${TIMESTAMP}" >&2
pg_dump --no-owner --no-privileges "$DATABASE_URL" | gzip -9 > "$DUMP_FILE"

# Optional client-side encryption example (uncomment to use age):
# age -r "$AGE_PUBLIC_KEY" -o "${DUMP_FILE}.age" "$DUMP_FILE" && mv "${DUMP_FILE}.age" "$DUMP_FILE"

echo "[+] Uploading to ${S3_PATH}" >&2
aws s3 cp "$DUMP_FILE" "$S3_PATH" --sse AES256 --metadata "created=${TIMESTAMP}" --tagging "retention=14d"

rm "$DUMP_FILE"

echo "[+] Verifying upload" >&2
aws s3 ls "$S3_PATH" >/dev/null || { echo "Upload verification failed" >&2; exit 1; }

echo "[+] Backup complete: ${S3_PATH}" >&2
