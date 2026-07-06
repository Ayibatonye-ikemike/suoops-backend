"""
One-time feature announcement broadcast.

Announces the storefront + online-payments launch (flat 3%, no plans) to
existing users via email (always) and WhatsApp. The WhatsApp side reuses the
already-approved morning-tip template (``WHATSAPP_TEMPLATE_MORNING_TIP`` —
params: name, headline, body), so no brand-new Meta template is needed.

Idempotent per user via ``UserEmailLog``, so it can be run repeatedly
(e.g. across several days to respect the WhatsApp budget) without
double-sending. Bump the ``_v1`` suffix on the tracking types to run a
brand-new announcement in the future.

Trigger from the admin panel: POST /admin/tasks/feature_announcement/trigger
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.db.session import session_scope
from app.utils.smtp import send_smtp_email
from app.workers.celery_app import celery_app
from app.workers.tasks.engagement_tasks import (
    _get_user_name,
    _record_sent,
    _send_wa_template,
    _was_sent,
)

logger = logging.getLogger(__name__)

_template_dir = Path(__file__).parent.parent.parent.parent / "templates" / "email"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_template_dir)),
    autoescape=select_autoescape(["html", "xml"]),
)

# Bump these suffixes to broadcast a future announcement.
ANNOUNCE_EMAIL_TYPE = "announce_online_storefront_v1"
ANNOUNCE_WA_TYPE = "wa_announce_online_storefront_v1"

_SUBJECT = "New: get paid online + your own storefront 🛍️"
_HEADLINE = "Two big new ways to get paid 🎉"
_CTA_URL = "https://suoops.com/dashboard/settings#online-payments"
_CTA_LABEL = "Turn it on →"

# WhatsApp copy (reuses the morning-tip template: {{1}} name, {{2}} headline,
# {{3}} body). Keep the body a single line — Meta rejects params with newlines.
_WA_HEADLINE = "🎉 New: get paid online + your storefront"
_WA_BODY = (
    "Customers can now pay you by card or transfer — it auto-confirms and settles "
    "to your bank the next business day (flat 3%, no monthly fee). You also get a "
    "shareable storefront link for all your products. Turn it on in Settings → Business: "
    "suoops.com/dashboard/settings"
)


def _plain_text(name: str) -> str:
    return (
        f"Hi {name},\n\n"
        "We just launched two things that make SuoOps even more useful — "
        "both included at a flat 3%, no plans to buy.\n\n"
        "💳 Get paid online — customers pay you by card or bank transfer. "
        "Payment auto-confirms and the money settles to your bank the next "
        "business day via Paystack. Flat 3% only when you get paid, no monthly fee. "
        "Your manual invoices are unchanged.\n\n"
        "🛍️ Your own storefront — a shareable page of all your products. Post "
        "the link on WhatsApp, Instagram or your bio and customers order and pay online.\n\n"
        f"Turn these on anytime: {_CTA_URL}\n\n"
        "— SuoOps"
    )


def _announce_to_user(db, user, stats: dict[str, int]) -> None:
    """Send the announcement to one user (email + best-effort WhatsApp)."""
    # Users already accepting online payments know about it — don't re-announce.
    if getattr(user, "paystack_subaccount_active", False):
        stats["skipped"] += 1
        return

    name = _get_user_name(user)

    if user.email and not _was_sent(db, user.id, ANNOUNCE_EMAIL_TYPE):
        html = _jinja_env.get_template("feature_announcement.html").render(
            name=name,
            headline=_HEADLINE,
            cta_url=_CTA_URL,
            cta_label=_CTA_LABEL,
        )
        if send_smtp_email(user.email, _SUBJECT, html, _plain_text(name)):
            _record_sent(db, user.id, ANNOUNCE_EMAIL_TYPE)
            stats["email_sent"] += 1
        else:
            stats["failed"] += 1

    # WhatsApp: reuse the already-approved morning-tip template (name, headline,
    # body) so no new Meta template is needed. Best-effort + budget-aware.
    wa_template = getattr(settings, "WHATSAPP_TEMPLATE_MORNING_TIP", None)
    if user.phone and wa_template:
        if _send_wa_template(
            user.phone,
            wa_template,
            [name, _WA_HEADLINE, _WA_BODY],
            ANNOUNCE_WA_TYPE,
            db,
            user.id,
        ):
            stats["whatsapp_sent"] += 1


@celery_app.task(
    name="announcement.send_feature_announcement",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=600,
    time_limit=660,
)
def send_feature_announcement(limit: int | None = None) -> dict[str, Any]:
    """Broadcast the storefront + online-payments announcement to existing users.

    Args:
        limit: Optional cap on how many users to process this run (useful for a
               test send). ``None`` processes everyone with an email address.

    Idempotent — users who already received it (or already use online payments)
    are skipped.
    """
    from app.models.models import User

    stats: dict[str, int] = {
        "email_sent": 0,
        "whatsapp_sent": 0,
        "skipped": 0,
        "failed": 0,
    }

    BATCH_SIZE = 50
    processed = 0

    try:
        with session_scope() as db:
            offset = 0
            while True:
                users = (
                    db.query(User)
                    .filter(User.email != None)  # noqa: E711
                    .order_by(User.id)
                    .offset(offset)
                    .limit(BATCH_SIZE)
                    .all()
                )
                if not users:
                    break

                for user in users:
                    try:
                        _announce_to_user(db, user, stats)
                    except Exception as e:
                        logger.warning("Announcement failed for user %s: %s", user.id, e)
                        stats["failed"] += 1
                    processed += 1
                    if limit and processed >= limit:
                        break

                db.commit()
                db.expire_all()

                if limit and processed >= limit:
                    break
                offset += BATCH_SIZE

        logger.info(
            "Feature announcement complete: email=%d whatsapp=%d skipped=%d failed=%d",
            stats["email_sent"],
            stats["whatsapp_sent"],
            stats["skipped"],
            stats["failed"],
        )
        return {"success": True, **stats}

    except Exception as exc:
        logger.error("Feature announcement task failed: %s", exc)
        raise
