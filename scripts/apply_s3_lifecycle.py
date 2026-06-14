#!/usr/bin/env python3
"""Apply S3 lifecycle rules to move old objects to Glacier.

Run once (idempotent):
    python scripts/apply_s3_lifecycle.py

Savings at 50K users:
  - Invoices >90d: $0.023 → $0.004/GB (~80% savings)
  - Receipts >180d: same
  - Tax reports >1yr: $0.023 → $0.0036/GB (~85% savings)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage.s3_client import S3Client

if __name__ == "__main__":
    client = S3Client()
    ok = client.ensure_lifecycle_policy()
    if ok:
        print("✅ S3 lifecycle policy applied successfully")
    else:
        print("❌ Failed to apply lifecycle policy (check logs)")
        sys.exit(1)
