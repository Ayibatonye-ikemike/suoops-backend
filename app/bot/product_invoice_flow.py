"""
Product-based invoice creation flow for WhatsApp bot.

Enables businesses to browse their inventory, add products to a cart,
and create invoices — all through WhatsApp interactive messages.

Flow:
    1. User sends "products" / "my products" / "stock" / "catalog"
    2. Bot shows interactive list of their products (with prices)
    3. User taps a product → bot asks quantity
    4. User replies with number → item added to cart
    5. Bot shows cart summary + [Add More] [Send Invoice] buttons
    6. "Send Invoice" → bot asks for customer name & phone
    7. User replies → invoice created with inventory-linked line items

All state is ephemeral (in-memory with TTL). No DB writes until invoice creation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.bot.whatsapp_client import WhatsAppClient
from app.models.inventory_models import Product
from app.services.inventory.product_service import ProductService

logger = logging.getLogger(__name__)

# Conversation state TTL (15 minutes)
CART_TTL_SECONDS = 900


@dataclass
class CartItem:
    """A product in the user's draft invoice cart."""
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class CartSession:
    """Ephemeral cart state for a WhatsApp user."""
    user_id: int          # DB user_id (issuer)
    items: list[CartItem] = field(default_factory=list)
    # Conversation step: "browsing" | "awaiting_qty" | "awaiting_customer"
    step: str = "browsing"
    # Product selected but quantity not yet given
    pending_product_id: int | None = None
    pending_product_name: str = ""
    pending_product_price: Decimal = Decimal("0")
    # Search query for filtering products
    search_query: str | None = None
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > CART_TTL_SECONDS

    @property
    def total(self) -> Decimal:
        return sum(item.line_total for item in self.items)

    @property
    def cart_summary(self) -> str:
        if not self.items:
            return "🛒 Cart is empty"
        lines = []
        for item in self.items:
            lines.append(f"  {item.quantity}x {item.product_name} — ₦{item.line_total:,.0f}")
        lines.append(f"\n💰 *Total: ₦{self.total:,.0f}*")
        return "🛒 *Your Cart:*\n" + "\n".join(lines)


# In-memory cart store (phone → CartSession)
# In production with multiple workers, use Redis. For single-worker Render, this is fine.
_carts: dict[str, CartSession] = {}


def get_cart(phone: str) -> CartSession | None:
    """Get active cart for phone, or None if expired/missing."""
    session = _carts.get(phone)
    if session and session.is_expired:
        del _carts[phone]
        return None
    return session


def clear_cart(phone: str) -> None:
    """Remove cart for phone."""
    _carts.pop(phone, None)


class ProductInvoiceFlow:
    """
    Handles the product-browsing → cart → invoice creation flow.

    Integrates with the existing InvoiceIntentProcessor for final creation.
    """

    # Keywords that trigger the product browsing flow
    TRIGGER_KEYWORDS = {"products", "my products", "stock", "catalog", "inventory", "shop"}

    def __init__(self, db: Session, client: WhatsAppClient):
        self.db = db
        self.client = client

    @staticmethod
    def is_trigger(text: str) -> bool:
        """Check if text triggers the product browsing flow."""
        return text.lower().strip() in ProductInvoiceFlow.TRIGGER_KEYWORDS

    @staticmethod
    def has_active_session(phone: str) -> bool:
        """Check if user has an active cart session (mid-flow)."""
        return get_cart(phone) is not None

    def start_browsing(self, phone: str, user_id: int, search: str | None = None) -> None:
        """
        Show the user's product catalog as a WhatsApp interactive list.

        Creates a new cart session and sends the product list.
        """
        product_svc = ProductService(self.db, user_id)
        products, total = product_svc.list_products(
            page=1,
            page_size=10,
            search=search,
        )

        if not products:
            if search:
                self.client.send_text(
                    phone,
                    f"🔍 No products found for \"{search}\".\n\n"
                    "Try a different keyword, or type *products* to see all."
                )
            else:
                self.client.send_text(
                    phone,
                    "📦 You have no products in your inventory yet.\n\n"
                    "Add products at suoops.com/dashboard/inventory\n"
                    "Then come back and type *products* to invoice from stock!"
                )
            return

        # Create/reset cart session
        session = CartSession(user_id=user_id, search_query=search)
        _carts[phone] = session

        # Build WhatsApp list rows (max 10)
        rows = []
        for product in products[:10]:
            price_str = f"₦{product.selling_price:,.0f}" if product.selling_price else "No price"
            stock_str = f" ({product.quantity_in_stock} in stock)" if product.track_stock else ""
            rows.append({
                "id": f"product_{product.id}",
                "title": product.name[:24],
                "description": f"{price_str}{stock_str}"[:72],
            })

        sections = [{"title": "Your Products", "rows": rows}]

        body = "📦 *Select a product to add to your invoice:*"
        if search:
            body = f"🔍 Results for \"{search}\":\n\n" + body

        footer = f"Showing {len(rows)} of {total} products"
        if total > 10:
            footer += " • Type 'search <name>' for more"

        self.client.send_interactive_list(
            to=phone,
            body=body,
            button_text="📋 View Products",
            sections=sections,
            header="SuoOps Inventory",
            footer=footer,
        )

    def handle_product_selected(self, phone: str, product_id: int) -> None:
        """User tapped a product from the list — ask for quantity."""
        session = get_cart(phone)
        if not session:
            self.client.send_text(phone, "⏰ Session expired. Type *products* to start again.")
            return

        product_svc = ProductService(self.db, session.user_id)
        product = product_svc.get_product(product_id)
        if not product:
            self.client.send_text(phone, "❌ Product not found. Type *products* to try again.")
            clear_cart(phone)
            return

        price_str = f"₦{product.selling_price:,.0f}" if product.selling_price else "No price set"
        stock_info = ""
        if product.track_stock:
            stock_info = f"\n📊 In stock: {product.quantity_in_stock}"

        session.step = "awaiting_qty"
        session.pending_product_id = product.id
        session.pending_product_name = product.name
        session.pending_product_price = product.selling_price or Decimal("0")

        self.client.send_text(
            phone,
            f"📦 *{product.name}*\n"
            f"💰 {price_str}{stock_info}\n\n"
            "How many? Reply with a number (e.g. *3*)"
        )

    def handle_quantity_reply(self, phone: str, text: str) -> None:
        """User replied with a quantity for the pending product."""
        session = get_cart(phone)
        if not session or session.step != "awaiting_qty":
            return

        # Parse quantity
        text = text.strip()
        try:
            qty = int(text)
            if qty <= 0:
                raise ValueError("Must be positive")
        except (ValueError, TypeError):
            self.client.send_text(
                phone,
                "❌ Please reply with a valid number (e.g. *3*)"
            )
            return

        # Check stock if tracked
        product_svc = ProductService(self.db, session.user_id)
        product = product_svc.get_product(session.pending_product_id)
        if product and product.track_stock and qty > product.quantity_in_stock:
            self.client.send_text(
                phone,
                f"⚠️ Only {product.quantity_in_stock} *{session.pending_product_name}* in stock.\n\n"
                f"Reply with a number up to {product.quantity_in_stock}, or type *products* to pick another."
            )
            return

        # Add to cart
        # Check if same product already in cart — update quantity
        existing = next((i for i in session.items if i.product_id == session.pending_product_id), None)
        if existing:
            existing.quantity += qty
        else:
            session.items.append(CartItem(
                product_id=session.pending_product_id,
                product_name=session.pending_product_name,
                quantity=qty,
                unit_price=session.pending_product_price,
            ))

        session.step = "browsing"
        session.pending_product_id = None

        line_total = session.pending_product_price * qty

        # Show cart and action buttons
        self.client.send_text(
            phone,
            f"✅ Added: {qty}x {session.pending_product_name} = ₦{line_total:,.0f}\n\n"
            f"{session.cart_summary}"
        )

        self.client.send_interactive_buttons(
            to=phone,
            body="What would you like to do?",
            buttons=[
                {"id": "cart_add_more", "title": "➕ Add More"},
                {"id": "cart_send_invoice", "title": "📄 Send Invoice"},
                {"id": "cart_clear", "title": "🗑️ Clear Cart"},
            ],
        )

    def handle_send_invoice(self, phone: str) -> None:
        """User tapped 'Send Invoice' — ask for customer details."""
        session = get_cart(phone)
        if not session or not session.items:
            self.client.send_text(phone, "🛒 Cart is empty. Type *products* to browse.")
            clear_cart(phone)
            return

        session.step = "awaiting_customer"
        self.client.send_text(
            phone,
            f"{session.cart_summary}\n\n"
            "👤 *Who is this invoice for?*\n\n"
            "Reply with customer name and phone:\n"
            "e.g. *Joy 08012345678*"
        )

    def handle_customer_reply(self, phone: str, text: str) -> dict[str, Any] | None:
        """
        User replied with customer details — build invoice data dict.

        Returns the invoice data dict ready for InvoiceIntentProcessor,
        or None if parsing failed.
        """
        session = get_cart(phone)
        if not session or session.step != "awaiting_customer":
            return None

        # Parse customer name and phone from text
        from app.bot.nlp_service import NLPService
        nlp = NLPService()
        customer_phone = nlp._extract_phone(text)
        customer_email = nlp._extract_email(text)

        # Extract name: first word that isn't a phone number
        tokens = text.strip().split()
        customer_name = "Customer"
        for token in tokens:
            clean = token.replace("+", "").replace("-", "").replace(",", "")
            if not clean.isdigit() and len(token) >= 2:
                customer_name = token.capitalize()
                break

        # Build line items with product_id for inventory integration
        lines = []
        for item in session.items:
            lines.append({
                "description": item.product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "product_id": item.product_id,
            })

        invoice_data = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "amount": session.total,
            "lines": lines,
            "due_date": None,
        }

        # Clear the cart
        clear_cart(phone)

        return invoice_data

    def handle_add_more(self, phone: str) -> None:
        """User tapped 'Add More' — show product list again."""
        session = get_cart(phone)
        if not session:
            self.client.send_text(phone, "⏰ Session expired. Type *products* to start again.")
            return

        session.step = "browsing"
        self.start_browsing(phone, session.user_id, search=session.search_query)

    def handle_clear_cart(self, phone: str) -> None:
        """User tapped 'Clear Cart' — reset everything."""
        clear_cart(phone)
        self.client.send_text(phone, "🗑️ Cart cleared.\n\nType *products* to start again.")

    def handle_search(self, phone: str, user_id: int, query: str) -> None:
        """User typed 'search <query>' — filter products."""
        self.start_browsing(phone, user_id, search=query)
