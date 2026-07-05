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


class StorefrontOut(BaseModel):
    enabled: bool
    slug: str | None
    link: str | None
    description: str | None = None


class StoreOrderItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=50)


class StoreOrderIn(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=6, max_length=20)
    items: list[StoreOrderItem] = Field(min_length=1, max_length=20)


def _link_for(slug: str | None) -> str | None:
    return f"{settings.FRONTEND_URL}/store/{slug}" if slug else None


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
    return StorefrontOut(
        enabled=True, slug=slug, link=_link_for(slug),
        description=user.storefront_description,
    )


@router.patch("/storefront", response_model=StorefrontOut)
def update_storefront(
    payload: StorefrontUpdateIn,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontOut:
    """Update the storefront description (what the shop sells)."""
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.storefront_description = (payload.description or "").strip() or None
    db.commit()
    return StorefrontOut(
        enabled=bool(user.storefront_enabled),
        slug=user.storefront_slug,
        link=_link_for(user.storefront_slug) if user.storefront_enabled else None,
        description=user.storefront_description,
    )


@router.get("/storefront", response_model=StorefrontOut)
def get_storefront(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontOut:
    """Return the current storefront status + link for the logged-in business."""
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return StorefrontOut(
        enabled=bool(user.storefront_enabled),
        slug=user.storefront_slug,
        link=_link_for(user.storefront_slug) if user.storefront_enabled else None,
        description=user.storefront_description,
    )


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


@public_router.get("/store/{slug}")
@limiter.limit("30/minute")
def get_public_storefront(request: Request, slug: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    """Public: a business's shareable inventory catalog."""
    owner = (
        db.query(models.User)
        .filter(
            models.User.storefront_slug == slug.lower(),
            models.User.storefront_enabled.is_(True),
        )
        .first()
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Storefront not found")

    products = (
        db.query(Product)
        .filter(Product.user_id == owner.id, Product.is_active.is_(True))
        .order_by(Product.name.asc())
        .all()
    )

    return {
        "slug": slug.lower(),
        "business_name": owner.business_name or owner.name,
        "description": owner.storefront_description,
        "logo_url": _presign(owner.logo_url),
        "online_payments_enabled": bool(
            owner.paystack_subaccount_active and owner.paystack_subaccount_code
        ),
        "whatsapp_url": _wa_url(owner),
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": float(p.selling_price) if p.selling_price is not None else None,
                "unit": p.unit,
                "image_url": _presign(p.image_url),
                "in_stock": (not p.track_stock) or (p.quantity_in_stock > 0),
            }
            for p in products
        ],
    }


@public_router.get("/stores")
@limiter.limit("30/minute")
def list_public_stores(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    page: int = 1,
    page_size: int = 24,
) -> dict:
    """Public directory of eligible storefronts (for the landing page).

    Trust gate: only businesses that opted in AND have a logo AND verified bank
    (active Paystack subaccount) AND at least one active product are listed.
    """
    page = max(1, page)
    page_size = min(max(1, page_size), 48)

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
            models.User.storefront_slug.isnot(None),
            models.User.logo_url.isnot(None),
            models.User.paystack_subaccount_active.is_(True),
            models.User.id.in_(db.query(product_owner_ids)),
        )
    )

    total = base.with_entities(func.count(models.User.id)).scalar() or 0
    owners = (
        base.order_by(models.User.storefront_slug.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "stores": [
            {
                "slug": o.storefront_slug,
                "business_name": o.business_name or o.name,
                "logo_url": _presign(o.logo_url),
                "description": o.storefront_description,
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
