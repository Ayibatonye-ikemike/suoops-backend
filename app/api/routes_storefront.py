"""
Public storefront: a shareable catalog of a business's inventory.

A business opts in (``storefront_enabled``) and gets a vanity slug. Customers
open ``suoops.com/store/<slug>`` to browse the business's active products.
Read-only for now (browse + contact); online ordering reuses the invoice
"Pay Now" + subaccount flow added elsewhere.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Annotated
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.rate_limit import limiter
from app.api.routes_auth import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models import models
from app.models.inventory_models import Product

logger = logging.getLogger(__name__)

# Authenticated storefront management endpoints.
router = APIRouter()
# Public (unauthenticated) storefront endpoints.
public_router = APIRouter()

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:58] or "shop"


def _unique_slug(db: Session, base: str, user_id: int) -> str:
    """Return a slug unique across users (append -2, -3, ... if needed)."""
    candidate = base
    n = 1
    while True:
        existing = (
            db.query(models.User)
            .filter(models.User.storefront_slug == candidate, models.User.id != user_id)
            .first()
        )
        if not existing:
            return candidate
        n += 1
        candidate = f"{base}-{n}"[:60]


def _presign(url: str | None) -> str | None:
    if not url:
        return None
    try:
        from app.storage.s3_client import s3_client

        key = s3_client.extract_key_from_url(url)
        if key:
            return s3_client.get_presigned_url(key, expires_in=3600) or url
    except Exception:  # noqa: BLE001
        pass
    return url


def _wa_url(user) -> str | None:
    """Public WhatsApp order link for the business (only if phone is verified)."""
    if not (getattr(user, "phone_verified", False) and getattr(user, "phone", None)):
        return None
    digits = re.sub(r"\D", "", user.phone)
    return f"https://wa.me/{digits}" if digits else None


class StorefrontEnableIn(BaseModel):
    slug: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=160)


class StorefrontUpdateIn(BaseModel):
    # Change the store URL slug. Not auto-derived from the business name (that
    # would break links already shared); the seller edits it deliberately.
    slug: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    # {"0": {"open": "09:00", "close": "18:00"}, ...} — 0=Mon; null day = closed.
    hours: dict | None = None
    announcement: str | None = Field(default=None, max_length=200)


class StorefrontOut(BaseModel):
    enabled: bool
    slug: str | None
    link: str | None
    description: str | None = None
    product_count: int = 0
    address: str | None = None
    city: str | None = None
    state: str | None = None
    lat: float | None = None
    lng: float | None = None
    hours: dict | None = None
    announcement: str | None = None
    views: int = 0


def _storefront_out(db: Session, user) -> StorefrontOut:
    """Build the owner-facing storefront payload from a user row."""
    return StorefrontOut(
        enabled=bool(user.storefront_enabled),
        slug=user.storefront_slug,
        link=_link_for(user.storefront_slug) if user.storefront_enabled else None,
        description=user.storefront_description,
        product_count=_product_count(db, user.id),
        address=user.storefront_address,
        city=user.storefront_city,
        state=user.storefront_state,
        lat=user.storefront_lat,
        lng=user.storefront_lng,
        hours=user.storefront_hours,
        announcement=user.storefront_announcement,
        views=user.storefront_views or 0,
    )


class StoreOrderItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=50)


class StoreOrderIn(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=6, max_length=20)
    items: list[StoreOrderItem] = Field(min_length=1, max_length=20)
    # Customer's GPS location (drives the buyer-protection window). Optional at
    # the API layer for backward-compat; the storefront UI captures it via GPS.
    customer_lat: float | None = Field(default=None, ge=-90, le=90)
    customer_lng: float | None = Field(default=None, ge=-180, le=180)
    # Optional landmark / delivery instructions the buyer can add so the
    # business can find them (the GPS pin is the primary delivery detail).
    delivery_note: str | None = Field(default=None, max_length=200)
    # Optional courier selection (buyer-pays-delivery). The server re-quotes and
    # validates the fee for this courier — the client can't set the price.
    delivery_courier_id: str | None = Field(default=None, max_length=60)
    delivery_service_code: str | None = Field(default=None, max_length=60)


def _link_for(slug: str | None) -> str | None:
    return f"{settings.FRONTEND_URL}/store/{slug}" if slug else None


def _product_count(db: Session, user_id: int) -> int:
    """Active products in the user's catalog (what the storefront displays)."""
    return (
        db.query(func.count(Product.id))
        .filter(Product.user_id == user_id, Product.is_active.is_(True))
        .scalar()
    ) or 0


_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def _clean_hours(hours: dict | None) -> dict | None:
    """Validate/normalise weekly hours to {"0".."6": {open, close}} (0=Mon).

    Storefronts may only open between 07:00 and 18:00 — times outside that range
    are clamped, and days where open is not before close are dropped.
    """
    if not hours:
        return None

    def _clamp(v: str) -> str:
        return "07:00" if v < "07:00" else "18:00" if v > "18:00" else v

    cleaned: dict[str, dict] = {}
    for day, val in hours.items():
        key = str(day)
        if key not in {"0", "1", "2", "3", "4", "5", "6"}:
            continue
        if not isinstance(val, dict):
            continue
        opn, cls = str(val.get("open", "")), str(val.get("close", ""))
        if _TIME_RE.match(opn) and _TIME_RE.match(cls):
            opn, cls = _clamp(opn), _clamp(cls)
            if opn < cls:  # ignore zero/negative-length days
                cleaned[key] = {"open": opn, "close": cls}
    return cleaned or None


def _open_now(hours: dict | None) -> tuple[bool, str | None, str | None]:
    """Return (is_open, today_open, today_close) in Africa/Lagos time."""
    if not hours:
        return (False, None, None)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Africa/Lagos"))
    today = hours.get(str(now.weekday()))
    if not today:
        return (False, None, None)
    opn, cls = today.get("open"), today.get("close")
    hm = now.strftime("%H:%M")
    is_open = bool(opn and cls and opn <= hm <= cls)
    return (is_open, opn, cls)


@router.post("/storefront/enable", response_model=StorefrontOut)
def enable_storefront(
    payload: StorefrontEnableIn,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontOut:
    """Enable the public storefront and return the shareable link."""
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.slug:
        slug = payload.slug.strip().lower()
        if not _SLUG_RE.match(slug):
            raise HTTPException(
                status_code=400,
                detail="Slug must be 3–60 chars: lowercase letters, numbers, hyphens.",
            )
    else:
        slug = user.storefront_slug or _slugify(user.business_name or user.name or f"shop-{user.id}")

    slug = _unique_slug(db, slug, user.id)

    user.storefront_slug = slug
    user.storefront_enabled = True
    if payload.description is not None:
        user.storefront_description = payload.description.strip() or None
    db.commit()
    logger.info("Storefront enabled for user %s -> %s", user.id, slug)
    return _storefront_out(db, user)


def _apply_storefront_profile(db: Session, user, payload: StorefrontUpdateIn) -> None:
    """Persist the optional storefront profile fields that were provided."""
    if payload.description is not None:
        user.storefront_description = payload.description.strip() or None
    if payload.address is not None:
        user.storefront_address = payload.address.strip() or None
    if payload.city is not None:
        user.storefront_city = payload.city.strip() or None
    if payload.state is not None:
        user.storefront_state = payload.state.strip() or None
    if payload.hours is not None:
        user.storefront_hours = _clean_hours(payload.hours)
    if payload.announcement is not None:
        user.storefront_announcement = payload.announcement.strip() or None


@router.patch("/storefront", response_model=StorefrontOut)
def update_storefront(
    payload: StorefrontUpdateIn,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontOut:
    """Update the storefront profile (description, location, hours, delivery…)."""
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Optional store-URL change (validated + made unique). Renaming the business
    # does NOT auto-change the slug, so existing links keep working.
    if payload.slug is not None:
        new_slug = _slugify(payload.slug)
        if not new_slug or new_slug == "shop":
            raise HTTPException(
                status_code=400,
                detail="Choose a valid store link — letters and numbers only.",
            )
        if new_slug != user.storefront_slug:
            user.storefront_slug = _unique_slug(db, new_slug, user.id)
    _apply_storefront_profile(db, user, payload)
    db.commit()
    return _storefront_out(db, user)


@router.get("/storefront", response_model=StorefrontOut)
def get_storefront(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontOut:
    """Return the current storefront status + link for the logged-in business."""
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _storefront_out(db, user)


class StorefrontLocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: float | None = None  # metres, from the GPS fix (informational)


@router.post("/storefront/location", response_model=StorefrontOut)
def set_storefront_location(
    payload: StorefrontLocationIn,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontOut:
    """Save the business's GPS location and derive its state on the SERVER.

    The client sends raw GPS coordinates; we reverse-geocode them ourselves so
    the state used for the escrow same/different-state window is trustworthy and
    can't be spoofed by the client.
    """
    from app.services.geocode_service import reverse_geocode

    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    state, city = reverse_geocode(payload.lat, payload.lng)
    user.storefront_lat = payload.lat
    user.storefront_lng = payload.lng
    if state:
        user.storefront_state = state
    if city:
        user.storefront_city = city
    db.commit()
    logger.info(
        "Storefront location set for user %s (state=%s, city=%s)", user.id, state, city
    )
    return _storefront_out(db, user)

@router.post("/storefront/disable", response_model=StorefrontOut)
def disable_storefront(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontOut:
    """Hide the public storefront (keeps the slug for later re-enable)."""
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.storefront_enabled = False
    db.commit()
    return StorefrontOut(enabled=False, slug=user.storefront_slug, link=None)


class ScanToPayOut(BaseModel):
    pay_url: str
    qr_png: str  # data:image/png;base64,... — display, print or share
    barcode: str


def _qr_data_url(data: str) -> str:
    """Render a URL as a scannable QR PNG (base64 data URL)."""
    import base64
    import io

    import qrcode

    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@router.get("/products/{product_id}/scan-to-pay", response_model=ScanToPayOut)
def product_scan_to_pay(
    product_id: int,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> ScanToPayOut:
    """Generate a scan-to-pay QR code for one product.

    Customers scan it to open the product on the business's storefront and pay
    online. The product's barcode is auto-generated on first use, so the
    business never has to type one. Requires the storefront to be enabled —
    that's where the customer actually pays.
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == current_user_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if not (user.storefront_enabled and user.storefront_slug):
        raise HTTPException(
            status_code=400,
            detail="Turn on your storefront first — that's where customers pay after scanning.",
        )

    # Auto-generate the barcode once, on demand (never manual for the user).
    if not (product.barcode or "").strip():
        import secrets

        product.barcode = "".join(secrets.choice("0123456789") for _ in range(12))
        db.commit()

    pay_url = f"{settings.FRONTEND_URL}/store/{user.storefront_slug}?p={product.id}"
    return ScanToPayOut(pay_url=pay_url, qr_png=_qr_data_url(pay_url), barcode=product.barcode)


class StorefrontQrOut(BaseModel):
    link: str
    qr_png: str  # data:image/png;base64,... — print, display or share


@router.get("/storefront/qr", response_model=StorefrontQrOut)
def storefront_qr(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontQrOut:
    """Shareable QR code that opens the whole storefront when scanned.

    Anyone who scans it lands on the business's public catalog and can browse
    and order. Requires the storefront to be enabled.
    """
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not (user.storefront_enabled and user.storefront_slug):
        raise HTTPException(
            status_code=400,
            detail="Turn on your storefront first to get a shareable QR code.",
        )
    link = _link_for(user.storefront_slug)
    return StorefrontQrOut(link=link, qr_png=_qr_data_url(link))


# ── Business-facing storefront order (escrow) status + delivery proof ──

def _escrow_summary(escrow: "models.StorefrontOrderEscrow", buyer: "models.Customer | None") -> dict:
    """Business-safe escrow summary. NEVER includes the buyer-only delivery code."""
    return {
        "status": escrow.status,
        "held": escrow.status == "held",
        "release_due_at": escrow.release_due_at.isoformat() if escrow.release_due_at else None,
        "confirmed_at": escrow.confirmed_at.isoformat() if escrow.confirmed_at else None,
        "delivered_at": (
            escrow.seller_marked_delivered_at.isoformat()
            if escrow.seller_marked_delivered_at
            else None
        ),
        "delivery_proof_note": escrow.delivery_proof_note,
        "delivery_proof_url": _presign(escrow.delivery_proof_url),
        "dispatched_at": (
            escrow.seller_dispatched_at.isoformat()
            if escrow.seller_dispatched_at
            else None
        ),
        "dispatch_tracking": escrow.dispatch_tracking,
        "dispatch_note": escrow.dispatch_note,
        "dispatch_carrier": escrow.dispatch_carrier,
        "dispatch_eta": escrow.dispatch_eta.isoformat() if escrow.dispatch_eta else None,
        "dispatch_tracking_url": escrow.shipbubble_tracking_url,
        "delivery_courier": escrow.delivery_courier,
        "delivery_service_type": escrow.delivery_service_type,
        "delivery_dropoff_station": escrow.delivery_dropoff_station,
        "dispatch_proof_url": _presign(escrow.dispatch_proof_url),
        "held_for_review": bool(escrow.held_for_review),
        "gross_naira": round((escrow.gross_kobo or 0) / 100, 2),
        "payout_naira": round((escrow.payout_kobo or 0) / 100, 2),
        "customer_name": buyer.name if buyer else None,
        "customer_phone": buyer.phone if buyer else None,
    }


def _load_owner_escrow(db: Session, user_id: int, invoice_public_id: str):
    """Return (escrow, buyer) for a storefront order owned by this user, or None."""
    row = (
        db.query(models.StorefrontOrderEscrow, models.Customer)
        .join(models.Invoice, models.StorefrontOrderEscrow.invoice_id == models.Invoice.id)
        .outerjoin(models.Customer, models.Invoice.customer_id == models.Customer.id)
        .filter(
            models.Invoice.invoice_id == invoice_public_id,
            models.StorefrontOrderEscrow.seller_id == user_id,
        )
        .first()
    )
    return row  # (escrow, customer) or None


@router.get("/storefront/orders/{invoice_id}")
def get_order_escrow(
    invoice_id: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Business: buyer-protection status for one of your storefront orders."""
    row = _load_owner_escrow(db, current_user_id, invoice_id)
    if not row:
        return {"escrow": None}
    escrow, buyer = row
    summary = _escrow_summary(escrow, buyer)
    # Buyer/system messages the seller hasn't opened yet (for the unread badge).
    summary["unread_messages"] = (
        db.query(func.count(models.OrderMessage.id))
        .filter(
            models.OrderMessage.escrow_id == escrow.id,
            models.OrderMessage.sender_role != "seller",
            models.OrderMessage.blocked.is_(False),
            models.OrderMessage.read_at.is_(None),
        )
        .scalar()
    ) or 0
    return {"escrow": summary}


async def _save_proof_photo(escrow: "models.StorefrontOrderEscrow", file: "UploadFile", *, prefix: str) -> str:
    """Validate + store a seller proof photo (delivery or dispatch) to S3.

    Shared by the mark-delivered and mark-sent endpoints: enforces image type,
    5MB cap and magic-byte check, then uploads under ``{prefix}/escrow_{id}.{ext}``.
    """
    from app.storage.s3_client import s3_client
    from app.utils.file_validation import get_safe_extension, validate_file_magic_bytes

    allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    if not file.content_type or file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Proof must be a PNG, JPG or WEBP image.")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image exceeds the 5MB limit.")
    if not validate_file_magic_bytes(content, file.content_type):
        raise HTTPException(status_code=400, detail="File content does not match its type.")
    ext = get_safe_extension(file.filename, file.content_type)
    key = f"{prefix}/escrow_{escrow.id}.{ext}"
    return await s3_client.upload_file(content, key, content_type=file.content_type)


@router.post("/storefront/orders/{invoice_id}/mark-delivered")
@limiter.limit("30/minute")
async def mark_order_delivered(
    request: Request,
    invoice_id: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    note: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Business: mark a storefront order delivered, with an optional proof photo.

    This is your evidence if the buyer later falsely claims non-delivery — it
    does NOT release funds (only the buyer's code or the window does that).
    """
    row = _load_owner_escrow(db, current_user_id, invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Order not found.")
    escrow, buyer = row

    import datetime as dt

    proof_url = escrow.delivery_proof_url
    if file is not None and file.filename:
        proof_url = await _save_proof_photo(escrow, file, prefix="delivery-proof")

    escrow.seller_marked_delivered_at = dt.datetime.now(dt.timezone.utc)
    if note is not None:
        escrow.delivery_proof_note = note.strip()[:255] or None
    escrow.delivery_proof_url = proof_url
    db.commit()
    db.refresh(escrow)
    logger.info("Seller %s marked order %s delivered", current_user_id, invoice_id)
    return {"escrow": _escrow_summary(escrow, buyer)}


@router.post("/storefront/orders/{invoice_id}/mark-sent")
@limiter.limit("30/minute")
async def mark_order_sent(
    request: Request,
    invoice_id: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    tracking: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
    carrier: Annotated[str | None, Form()] = None,
    eta: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Business: mark a storefront order SENT OUT (dispatched), with an optional
    courier/waybill tracking code, courier name, expected delivery date, and a
    photo of the packaged item.

    This is seller protection: timestamped proof you shipped a quality item,
    before the buyer confirms delivery. It also tells the buyer who's bringing
    their order and when to expect it. It does NOT release funds.
    """
    row = _load_owner_escrow(db, current_user_id, invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Order not found.")
    escrow, buyer = row

    import datetime as dt

    # A photo of the packaged item is REQUIRED — it's the proof of quality and
    # shipment (and the buyer sees it), so a "sent out" mark is never empty.
    if not (file is not None and file.filename) and not escrow.dispatch_proof_url:
        raise HTTPException(
            status_code=400, detail="A photo of the packaged item is required to mark it sent out."
        )

    proof_url = escrow.dispatch_proof_url
    if file is not None and file.filename:
        proof_url = await _save_proof_photo(escrow, file, prefix="dispatch-proof")

    # Auto-book the courier if the buyer paid for delivery at checkout and we
    # haven't booked yet. Best-effort: if booking fails the seller still marks
    # sent manually, so the flow never blocks on Shipbubble.
    if (
        settings.SHIPBUBBLE_CHECKOUT_ENABLED
        and escrow.delivery_request_token
        and escrow.delivery_courier_id
        and escrow.delivery_service_code
        and not escrow.shipbubble_order_id
    ):
        try:
            from app.services.shipping import shipbubble

            booking = shipbubble.create_shipment(
                request_token=escrow.delivery_request_token,
                courier_id=escrow.delivery_courier_id,
                service_code=escrow.delivery_service_code,
            )
            if booking and booking.get("order_id"):
                escrow.shipbubble_order_id = str(booking["order_id"])[:60]
                escrow.shipbubble_tracking_url = booking.get("tracking_url") or None
                if booking.get("courier") and not escrow.dispatch_carrier:
                    escrow.dispatch_carrier = str(booking["courier"])[:80]
                # Delivery-aware payout: don't auto-release until the courier
                # reports delivery. Cap the hold at the delivery SLA so a lost
                # parcel gets flagged for review instead of hanging forever.
                escrow.delivery_booked_at = dt.datetime.now(dt.timezone.utc)
                from app.services.escrow_service import add_business_days

                escrow.release_due_at = add_business_days(
                    dt.datetime.now(dt.timezone.utc),
                    settings.ESCROW_MAX_DELIVERY_DAYS,
                )
                logger.info(
                    "Booked Shipbubble shipment %s for order %s",
                    booking["order_id"], invoice_id,
                )
        except Exception:  # noqa: BLE001
            logger.exception("Shipbubble booking failed for order %s", invoice_id)

    escrow.seller_dispatched_at = dt.datetime.now(dt.timezone.utc)
    if tracking is not None:
        escrow.dispatch_tracking = tracking.strip()[:120] or None
    if note is not None:
        escrow.dispatch_note = note.strip()[:255] or None
    if carrier is not None:
        escrow.dispatch_carrier = carrier.strip()[:80] or None
    if eta is not None:
        # Accept an ISO date (YYYY-MM-DD); ignore anything unparseable.
        raw_eta = eta.strip()
        if raw_eta:
            try:
                escrow.dispatch_eta = dt.date.fromisoformat(raw_eta[:10])
            except ValueError:
                pass
        else:
            escrow.dispatch_eta = None
    escrow.dispatch_proof_url = proof_url
    db.commit()
    db.refresh(escrow)

    # Tell the buyer their order is on the way (system notice in the thread).
    try:
        parts = ["📦 Your order has been sent out."]
        if escrow.dispatch_carrier:
            parts.append(f"Courier: {escrow.dispatch_carrier}.")
        if escrow.dispatch_tracking:
            parts.append(f"Tracking: {escrow.dispatch_tracking}.")
        if escrow.dispatch_eta:
            parts.append(
                f"Expected delivery: {escrow.dispatch_eta.strftime('%a %d %b %Y')}."
            )
        _store_system_message(db, escrow, " ".join(parts))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to post dispatch notice for order %s", invoice_id)

    logger.info("Seller %s marked order %s sent out", current_user_id, invoice_id)
    return {"escrow": _escrow_summary(escrow, buyer)}


@public_router.get("/store/{slug}")
@limiter.limit("30/minute")
def get_public_storefront(request: Request, slug: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    """Public: a business's shareable inventory catalog."""
    from sqlalchemy.orm import joinedload

    owner = (
        db.query(models.User)
        .filter(
            models.User.storefront_slug == slug.lower(),
            models.User.storefront_enabled.is_(True),
            models.User.store_status == "active",
        )
        .first()
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Storefront not found")

    # Discovery analytics: count this view (best-effort, never blocks the page).
    try:
        owner.storefront_views = (owner.storefront_views or 0) + 1
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    products = (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(
            Product.user_id == owner.id,
            Product.is_active.is_(True),
            # Buyer protection: only list items that show a description AND a
            # photo, so buyers (and dispute reviews) can see exactly what was
            # ordered. Incomplete items are hidden until both are added.
            Product.description.isnot(None),
            Product.description != "",
            Product.image_url.isnot(None),
            Product.image_url != "",
        )
        .order_by(Product.name.asc())
        .all()
    )

    is_open, open_from, open_to = _open_now(owner.storefront_hours)

    reviews = (
        db.query(models.StorefrontReview)
        .filter(
            models.StorefrontReview.user_id == owner.id,
            models.StorefrontReview.approved.is_(True),
        )
        .all()
    )
    review_count = len(reviews)
    review_avg = round(sum(r.rating for r in reviews) / review_count, 1) if review_count else None

    address_parts = [owner.storefront_address, owner.storefront_city, owner.storefront_state]
    full_address = ", ".join(p for p in address_parts if p) or None

    return {
        "slug": slug.lower(),
        "business_name": owner.business_name or owner.name,
        "description": owner.storefront_description,
        "logo_url": _presign(owner.logo_url),
        "online_payments_enabled": bool(
            owner.paystack_subaccount_active and owner.paystack_subaccount_code
        ),
        "whatsapp_url": _wa_url(owner),
        "announcement": owner.storefront_announcement,
        "location": {
            "address": full_address,
            "city": owner.storefront_city,
            "state": owner.storefront_state,
            "maps_url": (
                f"https://www.google.com/maps/search/?api=1&query="
                f"{quote_plus(full_address)}"
                if full_address
                else None
            ),
        },
        "hours": owner.storefront_hours,
        "open_now": is_open,
        "open_from": open_from,
        "open_to": open_to,
        "reviews": {"count": review_count, "average": review_avg},
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": float(p.selling_price) if p.selling_price is not None else None,
                "unit": p.unit,
                "category": p.category.name if p.category else None,
                "image_url": _presign(p.image_url),
                "in_stock": (not p.track_stock) or (p.quantity_in_stock > 0),
            }
            for p in products
        ],
    }


def live_storefronts_query(db: Session):
    """Query for storefronts that are actually LIVE in the public directory.

    "Live" means a shopper can find the store via the global marketplace search:
    it must be opted-in, not suspended/delisted, have a logo, accept online
    payments (active Paystack subaccount) AND list at least one active product.
    This is the SAME trust gate used by ``list_public_stores`` — keep them in
    sync so admin metrics never disagree with what customers can see.
    """
    product_owner_ids = (
        db.query(Product.user_id).filter(Product.is_active.is_(True)).distinct().subquery()
    )
    return db.query(models.User).filter(
        models.User.storefront_enabled.is_(True),
        models.User.store_status == "active",
        models.User.storefront_slug.isnot(None),
        models.User.logo_url.isnot(None),
        models.User.paystack_subaccount_active.is_(True),
        models.User.id.in_(db.query(product_owner_ids)),
    )


def count_live_storefronts(db: Session) -> int:
    """Number of storefronts visible in the public marketplace/global search."""
    return live_storefronts_query(db).with_entities(func.count(models.User.id)).scalar() or 0


@public_router.get("/stores")
@limiter.limit("30/minute")
def list_public_stores(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    page: int = 1,
    page_size: int = 24,
    q: str | None = None,
) -> dict:
    """Public marketplace directory + global search across ALL stores.

    Trust gate: only businesses that opted in AND have a logo AND verified bank
    (active Paystack subaccount) AND at least one active product are listed.
    When ``q`` is given it searches business name, description, city/state and
    product names + categories across every store, so a shopper can find an item
    and pick which store to buy it from.
    """
    from sqlalchemy import or_

    from app.models.inventory_models import ProductCategory

    page = max(1, page)
    page_size = min(max(1, page_size), 48)
    term = (q or "").strip()

    # Owners with at least one active product.
    product_owner_ids = (
        db.query(Product.user_id)
        .filter(Product.is_active.is_(True))
        .distinct()
        .subquery()
    )

    base = (
        db.query(models.User)
        .filter(
            models.User.storefront_enabled.is_(True),
            models.User.store_status == "active",
            models.User.storefront_slug.isnot(None),
            models.User.logo_url.isnot(None),
            models.User.paystack_subaccount_active.is_(True),
            models.User.id.in_(db.query(product_owner_ids)),
        )
    )

    if term:
        like = f"%{term}%"
        product_match_ids = (
            db.query(Product.user_id)
            .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
            .filter(
                Product.is_active.is_(True),
                or_(Product.name.ilike(like), ProductCategory.name.ilike(like)),
            )
            .distinct()
            .subquery()
        )
        base = base.filter(
            or_(
                models.User.business_name.ilike(like),
                models.User.name.ilike(like),
                models.User.storefront_description.ilike(like),
                models.User.storefront_city.ilike(like),
                models.User.storefront_state.ilike(like),
                models.User.id.in_(db.query(product_match_ids)),
            )
        )

    total = base.with_entities(func.count(models.User.id)).scalar() or 0
    owners = (
        base.order_by(models.User.storefront_slug.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # For search results, surface up to 3 matching product names per store.
    matched: dict[int, list[str]] = {}
    if term and owners:
        like = f"%{term}%"
        rows = (
            db.query(Product.user_id, Product.name)
            .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
            .filter(
                Product.user_id.in_([o.id for o in owners]),
                Product.is_active.is_(True),
                or_(Product.name.ilike(like), ProductCategory.name.ilike(like)),
            )
            .all()
        )
        for uid, pname in rows:
            lst = matched.setdefault(uid, [])
            if len(lst) < 3 and pname not in lst:
                lst.append(pname)

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "query": term or None,
        "stores": [
            {
                "slug": o.storefront_slug,
                "business_name": o.business_name or o.name,
                "logo_url": _presign(o.logo_url),
                "description": o.storefront_description,
                "location": ", ".join(
                    p for p in [o.storefront_city, o.storefront_state] if p
                )
                or None,
                "matched_products": matched.get(o.id, []),
            }
            for o in owners
        ],
    }


@public_router.post("/store/{slug}/delivery-quote")
@limiter.limit("30/minute")
async def store_delivery_quote(
    request: Request,
    slug: str,
    payload: StoreOrderIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: live courier delivery options for a prospective order (buyer pays
    delivery). Returns ``{"enabled": False, "options": []}`` unless the Shipbubble
    integration is switched on with a key + funded wallet — so the manual dispatch
    flow is the default and nothing here can break checkout.

    NOTE: the enabled path talks to Shipbubble's sandbox/live API and must be
    verified against a real key + wallet before going live.
    """
    from app.services.shipping import shipbubble

    if not shipbubble.enabled():
        return {"enabled": False, "options": []}

    owner = (
        db.query(models.User)
        .filter(
            models.User.storefront_slug == slug.lower(),
            models.User.storefront_enabled.is_(True),
            models.User.store_status == "active",
        )
        .first()
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Storefront not found")

    quote = _shipbubble_quote(db, owner, payload) or {}
    return {
        "enabled": True,
        "request_token": quote.get("request_token"),
        "options": [o.as_dict() for o in quote.get("options", [])],
    }


def _shipbubble_quote(db: Session, owner: "models.User", payload: "StoreOrderIn"):
    """Validate both addresses and fetch live courier rates for this order.
    Returns ``{"request_token": str|None, "options": [DeliveryOption]}`` or None
    when the integration is off. Shared by the quote endpoint and checkout so the
    fee charged is always a fresh, server-verified rate (never a client value)."""
    from app.services.shipping import shipbubble

    if not shipbubble.enabled():
        return None

    seller_addr = ", ".join(
        p for p in [owner.storefront_city, owner.storefront_state, "Nigeria"] if p
    )
    sender_code = shipbubble.validate_address(
        name=owner.business_name or "Store",
        email=owner.email or "store@suoops.com",
        phone=owner.phone or "",
        address=seller_addr or "Nigeria",
        latitude=owner.storefront_lat,
        longitude=owner.storefront_lng,
    )
    buyer_digits = "".join(ch for ch in payload.customer_phone if ch.isdigit())
    receiver_code = shipbubble.validate_address(
        name=payload.customer_name,
        email=f"{buyer_digits or 'buyer'}@buyer.suoops.com",
        phone=payload.customer_phone,
        address=(payload.delivery_note or "customer location"),
        latitude=payload.customer_lat,
        longitude=payload.customer_lng,
    )
    if not (sender_code and receiver_code):
        return {"request_token": None, "options": []}

    prods = {
        p.id: p
        for p in db.query(Product)
        .filter(Product.id.in_([it.product_id for it in payload.items]))
        .all()
    }
    package_items = []
    for it in payload.items:
        p = prods.get(it.product_id)
        package_items.append(
            {
                "name": (getattr(p, "name", None) or "Item")[:60],
                "description": "order item",
                "unit_weight": str(getattr(p, "weight_kg", None) or 0.5),
                "unit_amount": str(int(getattr(p, "selling_price", 0) or 0)),
                "quantity": str(it.quantity),
            }
        )

    rates = shipbubble.fetch_rates(
        sender_address_code=sender_code,
        receiver_address_code=receiver_code,
        package_items=package_items,
    )
    return rates or {"request_token": None, "options": []}


@public_router.post("/store/{slug}/order")
@limiter.limit("20/hour")
async def create_store_order(
    request: Request,
    slug: str,
    payload: StoreOrderIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: place an online order from a storefront.

    Creates a pending, online-only invoice for the business (no invoice balance
    consumed) and returns a Paystack pay link. Storefront orders can only be
    paid online — that is how the platform earns its commission.
    """
    owner = (
        db.query(models.User)
        .filter(
            models.User.storefront_slug == slug.lower(),
            models.User.storefront_enabled.is_(True),
            models.User.store_status == "active",
        )
        .first()
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Storefront not found")

    if not (owner.paystack_subaccount_active and owner.paystack_subaccount_code):
        raise HTTPException(
            status_code=409, detail="This store isn't accepting online orders yet."
        )

    ids = [i.product_id for i in payload.items]
    products = (
        db.query(Product)
        .filter(
            Product.user_id == owner.id,
            Product.id.in_(ids),
            Product.is_active.is_(True),
            # Only complete (described + photographed) items are orderable.
            Product.description.isnot(None),
            Product.description != "",
            Product.image_url.isnot(None),
            Product.image_url != "",
        )
        .all()
    )
    pmap = {p.id: p for p in products}

    lines: list[dict] = []
    total = Decimal("0")
    for item in payload.items:
        product = pmap.get(item.product_id)
        if not product:
            raise HTTPException(status_code=400, detail="One or more products are unavailable.")
        if product.track_stock and product.quantity_in_stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"{product.name}: only {product.quantity_in_stock} in stock.",
            )
        price = product.selling_price or Decimal("0")
        lines.append(
            {
                "description": product.name,
                "quantity": item.quantity,
                "unit_price": price,
                "product_id": product.id,
            }
        )
        total += price * item.quantity

    if total <= 0:
        raise HTTPException(status_code=400, detail="Order total must be greater than zero.")

    from app.core.admin_security import get_client_ip
    from app.services.escrow_service import (
        create_order_escrow,
        detect_order_collusion,
        is_trusted_seller,
        seller_velocity_hold_reason,
    )

    # Decide hold vs normal settlement up front (drives caps + payment init).
    held = settings.ESCROW_ENABLED and not is_trusted_seller(db, owner)

    # Blast-radius caps for UNTRUSTED sellers: cap per-order value and the total
    # value held in-flight, so a scam/hijacked store can only ever touch so much.
    if held:
        order_kobo = int(total * 100)
        if order_kobo > settings.ESCROW_MAX_ORDER_NAIRA_UNTRUSTED * 100:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This store can't accept orders above ₦"
                    f"{settings.ESCROW_MAX_ORDER_NAIRA_UNTRUSTED:,} yet. "
                    "Please contact them directly for large orders."
                ),
            )
        inflight_kobo = (
            db.query(func.coalesce(func.sum(models.StorefrontOrderEscrow.gross_kobo), 0))
            .filter(
                models.StorefrontOrderEscrow.seller_id == owner.id,
                models.StorefrontOrderEscrow.status.in_(["pending", "held"]),
            )
            .scalar()
        ) or 0
        if inflight_kobo + order_kobo > settings.ESCROW_MAX_INFLIGHT_NAIRA_UNTRUSTED * 100:
            raise HTTPException(
                status_code=409,
                detail="This store has too many pending orders right now — please try again later.",
            )

    from app.services.invoice_payment_service import (
        PaymentInitError,
        start_invoice_payment,
    )
    from app.services.invoice_service import build_invoice_service

    # Buyer-pays-delivery (flag-gated, HELD orders only): re-quote the chosen
    # courier server-side so the fee can't be tampered, and add it to the amount
    # charged. The delivery fee is retained by SuoOps to fund the courier — it is
    # NOT part of the seller's goods total, so the seller is paid on goods only.
    delivery_fee = Decimal("0")
    delivery_sel: dict | None = None
    if settings.SHIPBUBBLE_CHECKOUT_ENABLED and held and payload.delivery_courier_id:
        quote = _shipbubble_quote(db, owner, payload) or {}
        token = quote.get("request_token")
        chosen = next(
            (
                o
                for o in quote.get("options", [])
                if str(o.courier_id) == str(payload.delivery_courier_id)
                and (
                    not payload.delivery_service_code
                    or o.service_code == payload.delivery_service_code
                )
            ),
            None,
        )
        if not (token and chosen):
            raise HTTPException(
                status_code=409,
                detail="That delivery option is no longer available — please pick a courier again.",
            )
        delivery_fee = Decimal(str(chosen.amount))
        station = chosen.dropoff_station or {}
        station_str = None
        if station:
            station_str = " — ".join(
                s for s in [station.get("name"), station.get("address")] if s
            )
            if station.get("phone"):
                station_str = f"{station_str} ({station['phone']})"
        delivery_sel = {
            "token": token,
            "courier_id": str(chosen.courier_id),
            "service_code": str(chosen.service_code),
            "courier": chosen.name,
            "service_type": chosen.service_type,
            "station": (station_str or None),
        }

    grand_total = total + delivery_fee

    svc = build_invoice_service(db)
    invoice = svc.create_invoice(
        owner.id,
        {
            "customer_name": payload.customer_name.strip(),
            "customer_phone": payload.customer_phone.strip(),
            "amount": grand_total,
            "currency": "NGN",
            "lines": lines,
            "channel": "storefront",
        },
        async_pdf=True,
        consume_balance=False,
    )

    # Surface delivery details to the business on the order/invoice. We send the
    # location as readable TEXT (reverse-geocoded address) so the seller can read
    # it in their notification, plus the GPS pin (a Google Maps link) for
    # turn-by-turn navigation. The buyer can add an optional landmark note.
    delivery_lines: list[str] = []
    if payload.customer_lat is not None and payload.customer_lng is not None:
        from app.services.geocode_service import reverse_geocode_address

        address = reverse_geocode_address(payload.customer_lat, payload.customer_lng)
        if address:
            delivery_lines.append(f"📍 Deliver to: {address}")
        delivery_lines.append(
            f"Map: https://www.google.com/maps?q="
            f"{payload.customer_lat},{payload.customer_lng}"
        )
    note = (payload.delivery_note or "").strip()
    if note:
        delivery_lines.append(f"Landmark/note: {note}")
    if delivery_lines:
        invoice.notes = "Storefront delivery\n" + "\n".join(delivery_lines)
        db.commit()

    try:
        pay = await start_invoice_payment(db, invoice, owner, hold=held)
    except PaymentInitError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # Only held orders get an escrow row (trusted sellers settle normally via
    # the subaccount split). Never let escrow bookkeeping break the order flow.
    delivery_code: str | None = None
    if held:
        try:
            # Self-dealing detection: buyer sharing the seller's IP / sitting on
            # the seller's own location → hold for admin review, never auto-release.
            review_reason = detect_order_collusion(
                owner,
                buyer_ip=get_client_ip(request),
                customer_lat=payload.customer_lat,
                customer_lng=payload.customer_lng,
                buyer_phone=payload.customer_phone,
            )
            # Velocity guard: recent settled volume / dispute rate also holds for
            # review (catches laundering spread across days).
            velocity_reason = seller_velocity_hold_reason(db, owner, total)
            review_reason = ", ".join(
                r for r in (review_reason, velocity_reason) if r
            ) or None
            if review_reason:
                review_reason = review_reason[:120]
            escrow = create_order_escrow(
                db,
                invoice=invoice,
                seller=owner,
                gross_naira=total,
                customer_lat=payload.customer_lat,
                customer_lng=payload.customer_lng,
                review_reason=review_reason,
            )
            delivery_code = escrow.confirmation_code
            if delivery_sel:
                # Retain the buyer's delivery fee to fund the courier; store the
                # selection so the shipment can be booked at "mark as sent".
                escrow.delivery_fee_kobo = int(delivery_fee * 100)
                escrow.delivery_courier = delivery_sel["courier"][:80]
                escrow.delivery_service_type = (delivery_sel.get("service_type") or None)
                escrow.delivery_dropoff_station = (
                    (delivery_sel.get("station") or None) and delivery_sel["station"][:300]
                )
                escrow.delivery_request_token = delivery_sel["token"][:200]
                escrow.delivery_courier_id = delivery_sel["courier_id"][:60]
                escrow.delivery_service_code = delivery_sel["service_code"][:60]
                db.commit()
            if review_reason:
                owner.flagged_for_review = True
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to create escrow hold for order %s", invoice.invoice_id)

    logger.info(
        "Storefront order %s created for store %s (user %s, held=%s)",
        invoice.invoice_id, slug, owner.id, held,
    )
    resp = {"invoice_id": invoice.invoice_id, **pay}
    if delivery_code:
        resp["delivery_code"] = delivery_code
    if delivery_fee > 0:
        resp["delivery_fee"] = float(delivery_fee)
    return resp


def _lookup_store(db: Session, slug: str):
    owner = (
        db.query(models.User)
        .filter(
            models.User.storefront_slug == slug.lower(),
            models.User.storefront_enabled.is_(True),
            models.User.store_status == "active",
        )
        .first()
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Storefront not found")
    return owner


class StockNotifyIn(BaseModel):
    product_id: int
    phone: str = Field(min_length=6, max_length=20)


@public_router.post("/store/{slug}/notify")
@limiter.limit("10/hour")
def notify_when_in_stock(
    request: Request,
    slug: str,
    payload: StockNotifyIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: capture a phone number to alert when a sold-out item returns."""
    owner = _lookup_store(db, slug)
    product = (
        db.query(Product)
        .filter(
            Product.id == payload.product_id,
            Product.user_id == owner.id,
            Product.is_active.is_(True),
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if (not product.track_stock) or (product.quantity_in_stock > 0):
        return {"ok": True, "message": "Good news — this item is available now."}

    phone = payload.phone.strip()
    exists = (
        db.query(models.StorefrontStockNotification)
        .filter(
            models.StorefrontStockNotification.product_id == product.id,
            models.StorefrontStockNotification.phone == phone,
            models.StorefrontStockNotification.notified.is_(False),
        )
        .first()
    )
    if not exists:
        db.add(
            models.StorefrontStockNotification(
                user_id=owner.id, product_id=product.id, phone=phone
            )
        )
        db.commit()
    return {"ok": True, "message": "We'll text you when it's back in stock."}


class ReviewIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)
    rating: int = Field(ge=1, le=5)
    text: str | None = Field(default=None, max_length=500)


@public_router.post("/store/{slug}/review")
@limiter.limit("10/hour")
def submit_review(
    request: Request,
    slug: str,
    payload: ReviewIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: leave a review — gated to customers who actually paid this store."""
    from app.utils.phone import normalize_phone

    owner = _lookup_store(db, slug)
    normalized = normalize_phone(payload.phone.strip())
    candidates = {payload.phone.strip(), normalized}

    paid = (
        db.query(models.Invoice)
        .join(models.Customer, models.Invoice.customer_id == models.Customer.id)
        .filter(
            models.Invoice.issuer_id == owner.id,
            models.Invoice.status == "paid",
            models.Customer.phone.in_(candidates),
        )
        .order_by(models.Invoice.id.desc())
        .first()
    )
    if not paid:
        raise HTTPException(
            status_code=403,
            detail="Only customers who've completed a paid order here can leave a review.",
        )

    customer = paid.customer
    existing = (
        db.query(models.StorefrontReview)
        .filter(
            models.StorefrontReview.user_id == owner.id,
            models.StorefrontReview.customer_id == customer.id,
        )
        .first()
    )
    text = (payload.text or "").strip() or None
    if existing:
        existing.rating = payload.rating
        existing.text = text
    else:
        db.add(
            models.StorefrontReview(
                user_id=owner.id,
                customer_id=customer.id,
                rating=payload.rating,
                text=text,
                reviewer_name=(customer.name or "Customer")[:100],
            )
        )
    db.commit()
    return {"ok": True, "message": "Thanks for your review!"}


@public_router.get("/store/{slug}/reviews")
@limiter.limit("30/minute")
def list_reviews(
    request: Request,
    slug: str,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: approved reviews for a storefront."""
    owner = _lookup_store(db, slug)
    rows = (
        db.query(models.StorefrontReview)
        .filter(
            models.StorefrontReview.user_id == owner.id,
            models.StorefrontReview.approved.is_(True),
        )
        .order_by(models.StorefrontReview.created_at.desc())
        .limit(50)
        .all()
    )
    count = len(rows)
    average = round(sum(r.rating for r in rows) / count, 1) if count else None
    return {
        "count": count,
        "average": average,
        "reviews": [
            {
                "rating": r.rating,
                "text": r.text,
                "name": r.reviewer_name or "Customer",
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


class ConfirmDeliveryIn(BaseModel):
    # The buyer-only delivery code (sent to the buyer, shown at checkout). Only
    # someone who physically received the order should know it — so a hijacked
    # store can't self-confirm delivery to release funds early.
    code: str = Field(min_length=4, max_length=12)


@public_router.post("/store/{slug}/confirm-delivery")
@limiter.limit("20/hour")
def confirm_delivery(
    request: Request,
    slug: str,
    payload: ConfirmDeliveryIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: confirm delivery with the buyer's delivery code → ends the
    buyer-protection window early. The seller is paid on our T+1 settlement
    cadence (the next daily settlement run), never same-day.

    The code is only ever shown to the buyer, so the seller can't self-release.
    """
    import datetime as dt

    from app.services.escrow_code_guard import (
        clear_code_failures,
        is_code_locked,
        register_code_failure,
    )

    owner = _lookup_store(db, slug)
    if is_code_locked(owner.id):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts on this store. Please try again later.",
        )
    code = payload.code.strip()

    escrow = (
        db.query(models.StorefrontOrderEscrow)
        .filter(
            models.StorefrontOrderEscrow.seller_id == owner.id,
            models.StorefrontOrderEscrow.confirmation_code == code,
        )
        .order_by(models.StorefrontOrderEscrow.id.desc())
        .first()
    )

    if not escrow:
        register_code_failure(owner.id)
        logger.warning("Invalid delivery-code attempt on store %s", slug)
        raise HTTPException(status_code=404, detail="That delivery code isn't valid.")
    clear_code_failures(owner.id)

    if escrow.status == "released":
        return {"ok": True, "message": "This order was already completed — thank you!"}
    if escrow.status == "refunded":
        return {"ok": True, "message": "You've already been refunded for this order."}
    if escrow.status != "held":
        raise HTTPException(
            status_code=409,
            detail="This order can't be confirmed right now.",
        )
    if escrow.held_for_review:
        # A flagged order shouldn't release on a code — it's under review.
        raise HTTPException(
            status_code=409,
            detail="This order is under review. Our team will be in touch.",
        )

    escrow.confirmed_at = dt.datetime.now(dt.timezone.utc)
    db.commit()

    # Confirmation ENDS buyer protection, but the payout follows our T+1
    # settlement cadence — the daily settlement run pays the seller (never
    # same-day), funded by settled collections. No transfer is initiated here.
    return {
        "ok": True,
        "message": "Thank you for confirming! The seller will be settled in our next payout run.",
    }


class OrderProblemIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)
    reason: str = Field(min_length=3, max_length=255)
    invoice_id: str | None = Field(default=None, max_length=40)


@public_router.post("/store/{slug}/report-problem")
@limiter.limit("10/hour")
def report_order_problem(
    request: Request,
    slug: str,
    payload: OrderProblemIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: the buyer reports a problem with a held order (e.g. never
    delivered, wrong item). Puts the hold into ``disputed`` so no auto-payout
    happens, and flags the seller for a Trust & Safety review. Gated by the
    buyer's phone number.
    """
    import datetime as dt

    from app.utils.phone import normalize_phone

    owner = _lookup_store(db, slug)
    normalized = normalize_phone(payload.phone.strip())
    candidates = {payload.phone.strip(), normalized}

    q = (
        db.query(models.StorefrontOrderEscrow)
        .join(models.Invoice, models.StorefrontOrderEscrow.invoice_id == models.Invoice.id)
        .join(models.Customer, models.Invoice.customer_id == models.Customer.id)
        .filter(
            models.StorefrontOrderEscrow.seller_id == owner.id,
            models.Customer.phone.in_(candidates),
        )
    )
    if payload.invoice_id:
        q = q.filter(models.Invoice.invoice_id == payload.invoice_id.strip())
    escrow = q.order_by(models.StorefrontOrderEscrow.id.desc()).first()

    if not escrow:
        raise HTTPException(
            status_code=404,
            detail="We couldn't find a held order for that phone number.",
        )

    if escrow.status == "refunded":
        return {"ok": True, "message": "You've already been refunded for this order."}
    if escrow.status == "released":
        raise HTTPException(
            status_code=409,
            detail="This order was already completed. Please contact support@suoops.com.",
        )
    if escrow.status == "disputed":
        return {"ok": True, "message": "We've already got your report — our team is on it."}
    if escrow.status != "held":
        raise HTTPException(status_code=409, detail="This order can't be reported right now.")

    escrow.status = "disputed"
    escrow.disputed_at = dt.datetime.now(dt.timezone.utc)
    escrow.dispute_reason = payload.reason.strip()[:255]
    # Flag the seller so it surfaces in the Trust & Safety review queue.
    owner.flagged_for_review = True
    db.commit()

    # Track the buyer's dispute history (deters serial false "not delivered" claims).
    try:
        from app.services.escrow_service import record_buyer_dispute

        record_buyer_dispute(db, payload.phone)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to record buyer dispute for %s", slug)

    logger.info(
        "Escrow %s disputed by buyer for store %s (seller %s)",
        escrow.id, slug, owner.id,
    )
    return {
        "ok": True,
        "message": "Thanks for letting us know. Your payment is safe and our team will review this.",
    }


# ── Order-scoped messaging (guarded buyer/seller chat) ─────────────────────────
# Delivery-coordination only, and only while an order is live (held). Every
# message is scanned: leak vectors (contact/account/links + the delivery code)
# are masked, off-platform pushes are blocked, and seller circumvention attempts
# flag the store. This keeps the escrow + commission on-platform.

_MSG_MAX = 1000


class BuyerMessageIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)  # buyer-only delivery code
    body: str = Field(min_length=1, max_length=_MSG_MAX)


class BuyerThreadIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class SellerMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=_MSG_MAX)


def _escrow_by_code(db: Session, owner_id: int, code: str):
    return (
        db.query(models.StorefrontOrderEscrow)
        .filter(
            models.StorefrontOrderEscrow.seller_id == owner_id,
            models.StorefrontOrderEscrow.confirmation_code == code,
        )
        .order_by(models.StorefrontOrderEscrow.id.desc())
        .first()
    )


def _messaging_open(escrow: "models.StorefrontOrderEscrow") -> bool:
    # Only for a live (held) order — not before payment or after it closes.
    return escrow.status == "held"


def _msg_out(m: "models.OrderMessage", viewer_role: str) -> dict:
    return {
        "id": m.id,
        "sender_role": m.sender_role,
        "mine": m.sender_role == viewer_role,
        "body": m.body_redacted,
        "flagged": bool(m.flagged),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _buyer_order_view(escrow: "models.StorefrontOrderEscrow") -> dict:
    """Buyer-safe order status for the thread modal (dispatch/delivery updates).

    Lets the buyer see 'sent out' with the courier tracking + packaged-item
    photo, so they know their order is on the way.
    """
    return {
        "status": escrow.status,
        "dispatched_at": (
            escrow.seller_dispatched_at.isoformat() if escrow.seller_dispatched_at else None
        ),
        "dispatch_tracking": escrow.dispatch_tracking,
        "dispatch_carrier": escrow.dispatch_carrier,
        "dispatch_eta": escrow.dispatch_eta.isoformat() if escrow.dispatch_eta else None,
        "dispatch_tracking_url": escrow.shipbubble_tracking_url,
        "dispatch_proof_url": _presign(escrow.dispatch_proof_url),
        "delivered_at": (
            escrow.seller_marked_delivered_at.isoformat()
            if escrow.seller_marked_delivered_at
            else None
        ),
    }


def _thread(db: Session, escrow_id: int) -> list["models.OrderMessage"]:
    return (
        db.query(models.OrderMessage)
        .filter(
            models.OrderMessage.escrow_id == escrow_id,
            models.OrderMessage.blocked.is_(False),  # blocked = stored for audit, never delivered
        )
        .order_by(models.OrderMessage.id.asc())
        .all()
    )


def _mark_read(db: Session, escrow_id: int, sender_role: str) -> None:
    import datetime as dt

    (
        db.query(models.OrderMessage)
        .filter(
            models.OrderMessage.escrow_id == escrow_id,
            models.OrderMessage.sender_role == sender_role,
            models.OrderMessage.read_at.is_(None),
        )
        .update({models.OrderMessage.read_at: dt.datetime.now(dt.timezone.utc)}, synchronize_session=False)
    )
    db.commit()


def _store_message(db: Session, escrow, *, sender_role: str, sender_user_id: int | None, body: str):
    from app.services.message_guard import scan_message

    result = scan_message(body)
    m = models.OrderMessage(
        escrow_id=escrow.id,
        sender_role=sender_role,
        sender_user_id=sender_user_id,
        body_raw=body,
        body_redacted=("" if result.blocked else result.redacted),
        flagged=result.flagged,
        flag_reasons=(",".join(result.reasons) or None),
        blocked=result.blocked,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m, result


def _store_system_message(db: Session, escrow, body: str):
    """Insert a system notice into the order thread (never guard-redacted).

    Used for platform-generated updates (e.g. "order sent out") so tracking codes
    and links aren't masked the way buyer/seller messages are.
    """
    m = models.OrderMessage(
        escrow_id=escrow.id,
        sender_role="system",
        sender_user_id=None,
        body_raw=body,
        body_redacted=body,
        flagged=False,
        flag_reasons=None,
        blocked=False,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@public_router.post("/store/{slug}/messages")
@limiter.limit("20/hour")
def buyer_send_message(
    request: Request,
    slug: str,
    payload: BuyerMessageIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: buyer sends a message on their order, authenticated by the
    buyer-only delivery code."""
    from app.services.escrow_code_guard import (
        clear_code_failures,
        is_code_locked,
        register_code_failure,
    )

    owner = _lookup_store(db, slug)
    if is_code_locked(owner.id):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts on this store. Please try again later.",
        )
    escrow = _escrow_by_code(db, owner.id, payload.code.strip())
    if not escrow:
        register_code_failure(owner.id)
        logger.warning("Invalid delivery-code attempt (message) on store %s", slug)
        raise HTTPException(status_code=404, detail="That delivery code isn't valid.")
    clear_code_failures(owner.id)
    if not _messaging_open(escrow):
        raise HTTPException(status_code=409, detail="Messaging is closed for this order.")

    m, result = _store_message(db, escrow, sender_role="buyer", sender_user_id=None, body=payload.body)
    if result.blocked:
        return {
            "ok": False,
            "blocked": True,
            "message": "Keep payments and contact on SuoOps so you stay protected — that message wasn't sent.",
        }
    return {
        "ok": True,
        "message": _msg_out(m, "buyer"),
        "warning": "Some details were hidden to keep you protected." if result.flagged else None,
    }


@public_router.post("/store/{slug}/messages/list")
@limiter.limit("20/hour")
def buyer_list_messages(
    request: Request,
    slug: str,
    payload: BuyerThreadIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Public: buyer reads their order thread (delivery code = access)."""
    from app.services.escrow_code_guard import (
        clear_code_failures,
        is_code_locked,
        register_code_failure,
    )

    owner = _lookup_store(db, slug)
    if is_code_locked(owner.id):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts on this store. Please try again later.",
        )
    escrow = _escrow_by_code(db, owner.id, payload.code.strip())
    if not escrow:
        register_code_failure(owner.id)
        logger.warning("Invalid delivery-code attempt (thread) on store %s", slug)
        raise HTTPException(status_code=404, detail="That delivery code isn't valid.")
    clear_code_failures(owner.id)
    _mark_read(db, escrow.id, "seller")  # buyer has now seen the seller's messages
    return {
        "messages": [_msg_out(m, "buyer") for m in _thread(db, escrow.id)],
        "order": _buyer_order_view(escrow),
    }


@router.get("/storefront/orders/{invoice_id}/messages")
def seller_list_messages(
    invoice_id: str,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Seller reads the thread for one of their storefront orders."""
    row = _load_owner_escrow(db, current_user_id, invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    escrow, _buyer = row
    _mark_read(db, escrow.id, "buyer")
    return {"messages": [_msg_out(m, "seller") for m in _thread(db, escrow.id)]}


@router.post("/storefront/orders/{invoice_id}/messages")
def seller_send_message(
    invoice_id: str,
    payload: SellerMessageIn,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Seller replies on one of their storefront orders. Circumvention attempts
    (masked contact/account or off-platform pushes) flag the store."""
    row = _load_owner_escrow(db, current_user_id, invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    escrow, _buyer = row
    if not _messaging_open(escrow):
        raise HTTPException(status_code=409, detail="Messaging is closed for this order.")

    m, result = _store_message(
        db, escrow, sender_role="seller", sender_user_id=current_user_id, body=payload.body
    )
    if result.flagged:
        try:
            from app.services.escrow_service import record_seller_circumvention

            seller = db.query(models.User).filter(models.User.id == current_user_id).first()
            if seller:
                record_seller_circumvention(db, seller)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record seller circumvention for order %s", invoice_id)

    if result.blocked:
        return {
            "ok": False,
            "blocked": True,
            "message": "Payments and contact must stay on SuoOps. That message wasn't sent — repeated attempts flag your store.",
        }
    return {
        "ok": True,
        "message": _msg_out(m, "seller"),
        "warning": "Sharing contact or payment details off-platform is not allowed and was hidden." if result.flagged else None,
    }
