#!/usr/bin/env bash
# Upload audit.log to S3 with compression and integrity hash.
# Usage: AUDIT_S3_BUCKET=suoops-audit-logs ./scripts/audit/upload_audit_log_to_s3.sh
set -euo pipefail

: "${AUDIT_S3_BUCKET:?AUDIT_S3_BUCKET required}"
AUDIT_FILE="storage/audit.log"
[ -f "$AUDIT_FILE" ] || { echo "No audit log found at $AUDIT_FILE" >&2; exit 0; }

STAMP="$(date -u +%Y%m%d-%H%M%S)"
TMP_COPY="/tmp/audit_${STAMP}.log"
TMP_GZ="${TMP_COPY}.gz"
S3_KEY="audit/${STAMP}.log.gz"

cp "$AUDIT_FILE" "$TMP_COPY"
sha256sum "$TMP_COPY" | awk '{print $1}' > "${TMP_COPY}.sha256"
HASH=$(cat "${TMP_COPY}.sha256")

gzip -9 "$TMP_COPY"

aws s3 cp "$TMP_GZ" "s3://${AUDIT_S3_BUCKET}/${S3_KEY}" \
  --sse AES256 \
  --metadata "sha256=${HASH},created=${STAMP}" \
  --tagging "retention=12m"

echo "Uploaded audit log: s3://${AUDIT_S3_BUCKET}/${S3_KEY} (sha256=$HASH)" >&2

# Truncate original file (simple rotation)
: > "$AUDIT_FILE"

echo "Audit log rotated" >&2
