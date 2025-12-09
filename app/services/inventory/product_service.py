"""
Product Service - CRUD operations for products.

Follows SRP: Only handles product-related operations.
"""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.models.inventory_models import Product, ProductCategory, StockMovement, StockMovementType
from app.models.inventory_schemas import ProductCreate, ProductUpdate
from app.services.inventory.base import BaseInventoryService

logger = logging.getLogger(__name__)


class ProductService(BaseInventoryService):
    """
    Service for product operations.
    
    Handles CRUD operations for products in the catalog.
    Each user has their own product catalog with independent SKUs.
    """

    def create_product(self, data: ProductCreate) -> Product:
        """
        Create a new product.
        
        If initial stock is provided, also creates an opening stock movement.
        """
        # Check for duplicate SKU
        existing = self._db.query(Product).filter(
            Product.user_id == self._user_id,
            Product.sku == data.sku,
        ).first()
        if existing:
            raise ValueError(f"Product with SKU '{data.sku}' already exists")

        # Validate category if provided
        if data.category_id:
            category = self._db.query(ProductCategory).filter(
                ProductCategory.id == data.category_id,
                ProductCategory.user_id == self._user_id,
            ).first()
            if not category:
                raise ValueError(f"Category with ID {data.category_id} not found")

        product = Product(
            user_id=self._user_id,
            sku=data.sku,
            name=data.name,
            description=data.description,
            barcode=data.barcode,
            category_id=data.category_id,
            cost_price=data.cost_price,
            selling_price=data.selling_price,
            quantity_in_stock=data.quantity_in_stock,
            reorder_level=data.reorder_level,
            reorder_quantity=data.reorder_quantity,
            unit=data.unit,
            track_stock=data.track_stock,
            image_url=data.image_url,
        )
        self._db.add(product)
        self._db.flush()  # Get the product ID

        # Create opening stock movement if initial quantity > 0
        if data.quantity_in_stock > 0 and data.track_stock:
            movement = StockMovement(
                user_id=self._user_id,
                product_id=product.id,
                movement_type=StockMovementType.OPENING,
                quantity=data.quantity_in_stock,
                quantity_before=0,
                quantity_after=data.quantity_in_stock,
                unit_cost=data.cost_price,
                total_cost=data.cost_price * data.quantity_in_stock if data.cost_price else None,
                reason="Opening stock balance",
                created_by="system",
            )
            self._db.add(movement)

        self._db.commit()
        self._db.refresh(product)
        logger.info(f"Created product: {product.name} (sku={product.sku}) for user {self._user_id}")
        return product

    def get_product(self, product_id: int) -> Product | None:
        """Get a product by ID with category loaded."""
        return self._db.query(Product).options(
            joinedload(Product.category)
        ).filter(
            Product.id == product_id,
            Product.user_id == self._user_id,
        ).first()

    def get_product_by_sku(self, sku: str) -> Product | None:
        """Get a product by SKU."""
        return self._db.query(Product).filter(
            Product.user_id == self._user_id,
            Product.sku == sku,
        ).first()

    def get_product_by_barcode(self, barcode: str) -> Product | None:
        """Get a product by barcode."""
        return self._db.query(Product).filter(
            Product.user_id == self._user_id,
            Product.barcode == barcode,
        ).first()

    def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        category_id: int | None = None,
        search: str | None = None,
        include_inactive: bool = False,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
    ) -> tuple[Sequence[Product], int]:
        """
        List products with filtering and pagination.
        
        Returns a tuple of (products, total_count).
        """
        query = self._db.query(Product).options(
            joinedload(Product.category)
        ).filter(Product.user_id == self._user_id)

        if not include_inactive:
            query = query.filter(Product.is_active.is_(True))

        if category_id:
            query = query.filter(Product.category_id == category_id)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Product.name.ilike(search_term),
                    Product.sku.ilike(search_term),
                    Product.barcode.ilike(search_term),
                    Product.description.ilike(search_term),
                )
            )

        if low_stock_only:
            query = query.filter(
                Product.track_stock.is_(True),
                Product.quantity_in_stock <= Product.reorder_level,
                Product.quantity_in_stock > 0,
            )

        if out_of_stock_only:
            query = query.filter(
                Product.track_stock.is_(True),
                Product.quantity_in_stock <= 0,
            )

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        products = query.order_by(Product.name).offset(offset).limit(page_size).all()

        return products, total

    def update_product(self, product_id: int, data: ProductUpdate) -> Product | None:
        """Update a product."""
        product = self.get_product(product_id)
        if not product:
            return None

        update_data = data.model_dump(exclude_unset=True)
        
        # Validate unique SKU if changing
        if "sku" in update_data and update_data["sku"] != product.sku:
            existing = self._db.query(Product).filter(
                Product.user_id == self._user_id,
                Product.sku == update_data["sku"],
                Product.id != product_id,
            ).first()
            if existing:
                raise ValueError(f"Product with SKU '{update_data['sku']}' already exists")

        # Validate category if changing
        if "category_id" in update_data and update_data["category_id"]:
            category = self._db.query(ProductCategory).filter(
                ProductCategory.id == update_data["category_id"],
                ProductCategory.user_id == self._user_id,
            ).first()
            if not category:
                raise ValueError(f"Category with ID {update_data['category_id']} not found")

        for key, value in update_data.items():
            setattr(product, key, value)

        self._db.commit()
        self._db.refresh(product)
        logger.info(f"Updated product: {product.name} (id={product.id})")
        return product

    def delete_product(self, product_id: int) -> bool:
        """Soft delete a product (set is_active=False)."""
        product = self.get_product(product_id)
        if not product:
            return False

        product.is_active = False
        self._db.commit()
        logger.info(f"Deleted product: {product.name} (id={product.id})")
        return True
