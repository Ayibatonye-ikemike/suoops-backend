"""Read-only: your ACTUAL month-by-month P&L (real history, not a projection).

This is the "Actuals" your real financials come from: real commission earned
(from the DB) minus your real monthly costs (passed in, since infra/payroll/
marketing aren't in the DB). Use it to build the model's Actuals tab and to
re-anchor the projection to where the business really is.

Per calendar month it reports:
  - New signups        (users created that month)
  - Active sellers     (distinct businesses that created a revenue invoice)
  - Commission earned  (real 3% — same logic + exclusions + ceiling as the app)
  - Costs / Operating result / Cumulative   (using your cost inputs)

Read-only (SELECT only). Run on the Render shell:
    PYTHONPATH=. python scripts/historical_pnl.py \
        --months 12 --payroll-ngn 150000 --marketing-usd 200 --infra-usd 222 \
        --fx 1600 --exclude founder@example.com
"""
from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy import func, or_

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import models
from app.utils.feature_gate import platform_fee_kobo


def _excluded_ids(db) -> list[int]:
    raw = settings.METRICS_EXCLUDED_EMAILS
    if not raw:
        return []
    emails = {e.strip().lower() for e in raw.split(",") if e.strip()}
    if not emails:
        return []
    return [
        uid
        for (uid,) in db.query(models.User.id)
        .filter(func.lower(models.User.email).in_(emails))
        .all()
    ]


def _naira(v) -> str:
    v = float(v or 0)
    if abs(v) >= 1_000_000:
        return f"₦{v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"₦{v/1_000:.0f}k"
    return f"₦{v:,.0f}"


def _month_starts(n: int) -> list[dt.datetime]:
    now = dt.datetime.now(dt.timezone.utc)
    cur = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    for _ in range(n):
        out.append(cur)
        cur = (cur - dt.timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--payroll-ngn", type=float, default=150_000)
    ap.add_argument("--marketing-usd", type=float, default=200)
    ap.add_argument("--infra-usd", type=float, default=222)
    ap.add_argument("--fx", type=float, default=1600)
    ap.add_argument("--exclude", type=str, default="")
    args = ap.parse_args()

    if args.exclude:
        settings.METRICS_EXCLUDED_EMAILS = args.exclude  # type: ignore[attr-defined]

    monthly_cost = args.payroll_ngn + args.marketing_usd * args.fx + args.infra_usd * args.fx
    ceiling = settings.METRICS_MAX_INVOICE_NAIRA or 0

    Invoice = models.Invoice
    User = models.User

    with SessionLocal() as db:
        excl = _excluded_ids(db)

        def not_excl(q):
            return q.filter(Invoice.issuer_id.notin_(excl)) if excl else q

        def cap(q):
            return q.filter(Invoice.amount <= ceiling) if ceiling and ceiling > 0 else q

        print("=" * 90)
        print("SuoOps — ACTUAL monthly P&L (real history)")
        print(f"Monthly cost applied: {_naira(monthly_cost)}  "
              f"(payroll {_naira(args.payroll_ngn)} + mktg ${args.marketing_usd:.0f} "
              f"+ infra ${args.infra_usd:.0f} @ ₦{args.fx:.0f}/$)")
        print("=" * 90)
        hdr = (f"{'Month':<9}{'Signups':>8}{'Active':>8}{'Commission':>14}"
               f"{'Cost':>12}{'Op result':>14}{'Cumulative':>14}")
        print(hdr)
        print("-" * 90)

        cum = 0.0
        tot_comm = 0.0
        for ms in _month_starts(args.months):
            me = (ms + dt.timedelta(days=32)).replace(day=1)
            label = ms.strftime("%Y-%m")

            signups = db.query(func.count(User.id)).filter(
                User.created_at >= ms, User.created_at < me
            ).scalar() or 0

            active = not_excl(
                db.query(func.count(func.distinct(Invoice.issuer_id))).filter(
                    Invoice.invoice_type == "revenue",
                    Invoice.created_at >= ms,
                    Invoice.created_at < me,
                )
            ).scalar() or 0

            manual = cap(not_excl(
                db.query(Invoice.amount).filter(
                    Invoice.invoice_type == "revenue",
                    Invoice.created_at >= ms,
                    Invoice.created_at < me,
                    or_(Invoice.channel != "storefront", Invoice.channel.is_(None)),
                )
            )).all()
            online = cap(not_excl(
                db.query(Invoice.amount).filter(
                    Invoice.invoice_type == "revenue",
                    Invoice.channel == "storefront",
                    Invoice.status == "paid",
                    Invoice.paid_at >= ms,
                    Invoice.paid_at < me,
                )
            )).all()
            commission = (
                sum(platform_fee_kobo(a) for (a,) in manual)
                + sum(platform_fee_kobo(a) for (a,) in online)
            ) / 100

            # Only charge costs for months the business was actually operating
            # (i.e. from the first month with any signup or commission onward).
            operating = commission > 0 or signups > 0 or active > 0
            cost = monthly_cost if operating else 0
            op = commission - cost
            cum += op
            tot_comm += commission

            print(f"{label:<9}{signups:>8}{active:>8}{_naira(commission):>14}"
                  f"{_naira(cost):>12}{_naira(op):>14}{_naira(cum):>14}")

        print("-" * 90)
        print(f"{'TOTAL':<9}{'':>8}{'':>8}{_naira(tot_comm):>14}"
              f"{'':>12}{_naira(cum):>14}")
        print("=" * 90)
        print("Notes: commission is REAL (from the DB). Costs are your CURRENT run-rate")
        print("applied flat across operating months — adjust --payroll/--marketing/--infra")
        print("if they were different historically. This is your actuals; the projection")
        print("model is separate. Cumulative op result ≈ your net burn/profit to date.")


if __name__ == "__main__":
    main()
