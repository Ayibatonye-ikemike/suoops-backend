#!/usr/bin/env python3
"""Disable ALL recurring Paystack subscriptions ("cancel at our end").

Cancelling Pro plans inside SuoOps does NOT stop recurring card charges — those
come from subscriptions that are still ACTIVE on Paystack. This script talks to
Paystack directly, lists every subscription, and disables the ones that can still
bill a card (status "active" or "attention"). It also clears the stored
``paystack_subscription_code`` locally for any matched user.

Safe by default: DRY-RUN unless you pass --execute.

Usage (run where PAYSTACK_SECRET is set, e.g. the Render shell):
    python3 scripts/cancel_all_paystack_subscriptions.py            # report only
    python3 scripts/cancel_all_paystack_subscriptions.py --execute  # actually disable
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx

from app.core.config import settings

PAYSTACK_BASE = "https://api.paystack.co"
# Statuses that can still charge a card. "non-renewing" already won't renew;
# "completed"/"cancelled" are finished.
BILLABLE_STATUSES = {"active", "attention"}


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }


def _list_all_subscriptions(client: httpx.Client) -> list[dict]:
    """Page through every subscription on the Paystack account."""
    subs: list[dict] = []
    page = 1
    while True:
        resp = client.get(
            f"{PAYSTACK_BASE}/subscription",
            headers=_headers(),
            params={"perPage": 100, "page": page},
            timeout=30.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or []
        subs.extend(data)
        meta = payload.get("meta") or {}
        page_count = meta.get("pageCount") or 1
        if page >= page_count or not data:
            break
        page += 1
    return subs


def _email_token(client: httpx.Client, sub: dict) -> str | None:
    """Return the email_token needed to disable a subscription.

    It is usually present on the list item; if not, fetch the subscription.
    """
    token = sub.get("email_token")
    if token:
        return token
    code = sub.get("subscription_code")
    if not code:
        return None
    resp = client.get(
        f"{PAYSTACK_BASE}/subscription/{code}",
        headers=_headers(),
        timeout=30.0,
    )
    if resp.status_code != 200:
        return None
    return (resp.json().get("data") or {}).get("email_token")


def _disable(client: httpx.Client, code: str, token: str) -> tuple[bool, str]:
    resp = client.post(
        f"{PAYSTACK_BASE}/subscription/disable",
        headers=_headers(),
        json={"code": code, "token": token},
        timeout=30.0,
    )
    if resp.status_code == 200 and resp.json().get("status"):
        return True, "disabled"
    msg = ""
    try:
        msg = resp.json().get("message", resp.text)
    except Exception:
        msg = resp.text
    # Paystack returns an error if it's already inactive — treat as success.
    if "already" in msg.lower() and "inactive" in msg.lower():
        return True, "already inactive"
    return False, msg


def _clear_local_code(codes: list[str]) -> int:
    """Best-effort: null out paystack_subscription_code for matched users."""
    try:
        from app.db.session import SessionLocal
        from app.models.models import User
    except Exception as exc:  # pragma: no cover
        print(f"  (skipped local DB update: {exc})")
        return 0
    if not codes:
        return 0
    db = SessionLocal()
    updated = 0
    try:
        rows = (
            db.query(User)
            .filter(User.paystack_subscription_code.in_(codes))
            .all()
        )
        for u in rows:
            u.paystack_subscription_code = None
            updated += 1
        db.commit()
    except Exception as exc:  # pragma: no cover
        db.rollback()
        print(f"  (local DB update failed: {exc})")
    finally:
        db.close()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually disable subscriptions (default is a dry run/report only).",
    )
    args = parser.parse_args()

    if not getattr(settings, "PAYSTACK_SECRET", None):
        print("ERROR: PAYSTACK_SECRET is not set in this environment.")
        print("Run this on Render (or wherever the live Paystack secret lives).")
        return 2

    with httpx.Client() as client:
        print("Fetching all subscriptions from Paystack…")
        try:
            subs = _list_all_subscriptions(client)
        except httpx.HTTPStatusError as exc:
            print(f"ERROR listing subscriptions: {exc.response.status_code} {exc.response.text}")
            return 2

        billable = [s for s in subs if (s.get("status") or "").lower() in BILLABLE_STATUSES]

        print(f"\nTotal subscriptions on account: {len(subs)}")
        print(f"Still able to charge a card (status active/attention): {len(billable)}\n")

        if not billable:
            print("Nothing to cancel — no billable subscriptions found. ✅")
            return 0

        for s in billable:
            cust = (s.get("customer") or {}).get("email", "?")
            plan = (s.get("plan") or {}).get("name", "?")
            amount = (s.get("amount") or 0) / 100
            print(
                f"  • {s.get('subscription_code')}  {s.get('status'):9s}  "
                f"₦{amount:,.0f}  {plan}  {cust}"
            )

        if not args.execute:
            print(
                f"\nDRY RUN — nothing changed. Re-run with --execute to disable "
                f"these {len(billable)} subscription(s)."
            )
            return 0

        print(f"\nDisabling {len(billable)} subscription(s) on Paystack…\n")
        disabled_codes: list[str] = []
        failed = 0
        for s in billable:
            code = s.get("subscription_code")
            token = _email_token(client, s)
            if not code or not token:
                print(f"  ✗ {code}: missing code/email_token, skipped")
                failed += 1
                continue
            ok, detail = _disable(client, code, token)
            if ok:
                print(f"  ✓ {code}: {detail}")
                disabled_codes.append(code)
            else:
                print(f"  ✗ {code}: {detail}")
                failed += 1
            time.sleep(0.2)  # be gentle on the API

        cleared = _clear_local_code(disabled_codes)
        print(
            f"\nDone. Disabled: {len(disabled_codes)}  Failed: {failed}  "
            f"Local codes cleared: {cleared}"
        )
        if failed:
            print("Some failed — re-run the script to retry the stragglers.")
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
