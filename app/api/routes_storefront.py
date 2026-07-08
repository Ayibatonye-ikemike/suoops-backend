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

from fastapi import APIRouter, Depends, HTTPException, Request
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
    """Validate/normalise weekly hours to {"0".."6": {open, close}} (0=Mon)."""
    if not hours:
        return None
    cleaned: dict[str, dict] = {}
    for day, val in hours.items():
        key = str(day)
        if key not in {"0", "1", "2", "3", "4", "5", "6"}:
            continue
        if not isinstance(val, dict):
            continue
        opn, cls = str(val.get("open", "")), str(val.get("close", ""))
        if _TIME_RE.match(opn) and _TIME_RE.match(cls):
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
        .filter(Product.user_id == owner.id, Product.is_active.is_(True))
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

    from app.services.invoice_payment_service import (
        PaymentInitError,
        start_invoice_payment,
    )
    from app.services.invoice_service import build_invoice_service

    svc = build_invoice_service(db)
    invoice = svc.create_invoice(
        owner.id,
        {
            "customer_name": payload.customer_name.strip(),
            "customer_phone": payload.customer_phone.strip(),
            "amount": total,
            "currency": "NGN",
            "lines": lines,
            "channel": "storefront",
        },
        async_pdf=True,
        consume_balance=False,
    )

    try:
        pay = await start_invoice_payment(db, invoice, owner)
    except PaymentInitError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    logger.info(
        "Storefront order %s created for store %s (user %s)",
        invoice.invoice_id, slug, owner.id,
    )
    return {"invoice_id": invoice.invoice_id, **pay}


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
