"""
Inventory Service - Business logic for inventory management.

Follows OOP principles:
- Single Responsibility: Each method handles one specific operation
- Dependency Injection: Database session injected via constructor
- Encapsulation: Internal helpers are private methods
- Interface Segregation: Clear separation between product, stock, and analytics operations
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select, and_, or_
from sqlalchemy.orm import Session, joinedload

from app.models.inventory_models import (
    Product,
    ProductCategory,
    StockMovement,
    StockMovementType,
    Supplier,
)
from app.models.inventory_schemas import (
    ProductCreate,
    ProductUpdate,
    ProductCategoryCreate,
    ProductCategoryUpdate,
    SupplierCreate,
    SupplierUpdate,
    StockAdjustmentCreate,
    InventorySummary,
    LowStockAlert,
)

logger = logging.getLogger(__name__)


class InventoryService:
    """
    Service class for inventory management operations.
    
    Handles all business logic related to products, stock movements,
    categories, and suppliers. Maintains data integrity and audit trails.
    """

    def __init__(self, db: Session, user_id: int):
        """
        Initialize the inventory service.
        
        Args:
            db: SQLAlchemy database session
            user_id: ID of the authenticated user (business owner)
        """
        self._db = db
        self._user_id = user_id

    # ========================================================================
    # Product Category Operations
    # ========================================================================

    def create_category(self, data: ProductCategoryCreate) -> ProductCategory:
        """Create a new product category."""
        category = ProductCategory(
            user_id=self._user_id,
            name=data.name,
            description=data.description,
            color=data.color,
        )
        self._db.add(category)
        self._db.commit()
        self._db.refresh(category)
        logger.info(f"Created category: {category.name} (id={category.id}) for user {self._user_id}")
        return category

    def get_category(self, category_id: int) -> ProductCategory | None:
        """Get a category by ID."""
        return self._db.query(ProductCategory).filter(
            ProductCategory.id == category_id,
            ProductCategory.user_id == self._user_id,
        ).first()

    def list_categories(self, include_inactive: bool = False) -> Sequence[ProductCategory]:
        """List all categories for the user."""
        query = self._db.query(ProductCategory).filter(
            ProductCategory.user_id == self._user_id,
        )
        if not include_inactive:
            query = query.filter(ProductCategory.is_active == True)
        return query.order_by(ProductCategory.name).all()

    def update_category(self, category_id: int, data: ProductCategoryUpdate) -> ProductCategory | None:
        """Update a category."""
        category = self.get_category(category_id)
        if not category:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(category, key, value)
        
        self._db.commit()
        self._db.refresh(category)
        logger.info(f"Updated category: {category.name} (id={category.id})")
        return category

    def delete_category(self, category_id: int) -> bool:
        """Soft delete a category (set is_active=False)."""
        category = self.get_category(category_id)
        if not category:
            return False
        
        category.is_active = False
        self._db.commit()
        logger.info(f"Deleted category: {category.name} (id={category.id})")
        return True

    # ========================================================================
    # Product Operations
    # ========================================================================

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
            category = self.get_category(data.category_id)
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
            query = query.filter(Product.is_active == True)

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
                Product.track_stock == True,
                Product.quantity_in_stock <= Product.reorder_level,
                Product.quantity_in_stock > 0,
            )

        if out_of_stock_only:
            query = query.filter(
                Product.track_stock == True,
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
            category = self.get_category(update_data["category_id"])
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

    # ========================================================================
    # Stock Movement Operations
    # ========================================================================

    def adjust_stock(self, data: StockAdjustmentCreate, created_by: str = "user") -> StockMovement:
        """
        Adjust stock for a product.
        
        Creates a stock movement record and updates the product quantity.
        """
        product = self.get_product(data.product_id)
        if not product:
            raise ValueError(f"Product with ID {data.product_id} not found")

        if not product.track_stock:
            raise ValueError(f"Stock tracking is disabled for product '{product.name}'")

        quantity_before = product.quantity_in_stock
        
        # Apply the stock change
        try:
            product.adjust_stock(data.quantity)
        except ValueError as e:
            raise ValueError(str(e))

        quantity_after = product.quantity_in_stock

        # Create movement record
        movement = StockMovement(
            user_id=self._user_id,
            product_id=product.id,
            movement_type=StockMovementType(data.movement_type),
            quantity=data.quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            unit_cost=data.unit_cost or product.cost_price,
            total_cost=(data.unit_cost or product.cost_price or Decimal(0)) * abs(data.quantity),
            reason=data.reason,
            notes=data.notes,
            created_by=created_by,
        )
        self._db.add(movement)
        self._db.commit()
        self._db.refresh(movement)

        logger.info(
            f"Stock adjusted for {product.name}: {quantity_before} -> {quantity_after} "
            f"(change: {data.quantity}, type: {data.movement_type})"
        )
        return movement

    def record_sale(
        self,
        product_id: int,
        quantity: int,
        unit_price: Decimal,
        invoice_line_id: int | None = None,
        reference_id: str | None = None,
    ) -> StockMovement | None:
        """
        Record a sale and deduct stock.
        
        Called when an invoice is created with line items linked to products.
        Returns None if product doesn't track stock.
        """
        product = self.get_product(product_id)
        if not product or not product.track_stock:
            return None

        quantity_before = product.quantity_in_stock
        
        try:
            product.adjust_stock(-quantity)  # Negative for sales
        except ValueError:
            raise ValueError(f"Insufficient stock for product '{product.name}'. Available: {product.quantity_in_stock}, Requested: {quantity}")

        quantity_after = product.quantity_in_stock

        movement = StockMovement(
            user_id=self._user_id,
            product_id=product.id,
            movement_type=StockMovementType.SALE,
            quantity=-quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            unit_cost=unit_price,
            total_cost=unit_price * quantity,
            reference_type="invoice",
            reference_id=reference_id,
            invoice_line_id=invoice_line_id,
            reason="Invoice sale",
            created_by="system",
        )
        self._db.add(movement)
        self._db.commit()
        self._db.refresh(movement)

        logger.info(f"Sale recorded for {product.name}: {quantity_before} -> {quantity_after}")
        return movement

    def record_purchase(
        self,
        product_id: int,
        quantity: int,
        unit_cost: Decimal,
        expense_id: int | None = None,
        reference_id: str | None = None,
        supplier_id: int | None = None,
    ) -> StockMovement | None:
        """
        Record a purchase and add stock.
        
        Called when an expense/receipt with inventory items is created.
        This enables automatic stock replenishment from expense tracking.
        
        Args:
            product_id: ID of the product to add stock to
            quantity: Quantity being purchased (positive)
            unit_cost: Cost per unit
            expense_id: Optional expense/receipt ID for audit trail
            reference_id: Optional invoice/expense reference string
            supplier_id: Optional supplier ID
            
        Returns:
            StockMovement record or None if product doesn't track stock
        """
        product = self.get_product(product_id)
        if not product or not product.track_stock:
            return None

        quantity_before = product.quantity_in_stock
        product.adjust_stock(quantity)  # Positive for purchases
        quantity_after = product.quantity_in_stock

        # Update cost price if provided (weighted average or replace)
        if unit_cost and unit_cost > 0:
            product.cost_price = unit_cost

        movement = StockMovement(
            user_id=self._user_id,
            product_id=product.id,
            movement_type=StockMovementType.PURCHASE,
            quantity=quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            unit_cost=unit_cost,
            total_cost=unit_cost * quantity,
            reference_type="expense" if expense_id else "manual",
            reference_id=reference_id,
            supplier_id=supplier_id,
            reason="Expense purchase" if expense_id else "Manual purchase",
            created_by="system",
        )
        self._db.add(movement)
        self._db.commit()
        self._db.refresh(movement)

        logger.info(f"Purchase recorded for {product.name}: {quantity_before} -> {quantity_after}")
        return movement

    def process_invoice_lines(
        self,
        invoice_id: int,
        invoice_ref: str,
        lines: list[dict],
        is_expense: bool = False,
    ) -> list[StockMovement]:
        """
        Process invoice lines and update inventory accordingly.
        
        For revenue invoices: Deduct stock (sales)
        For expense invoices: Add stock (purchases)
        
        This is the main automation hook called from invoice creation.
        
        Args:
            invoice_id: Invoice ID for reference
            invoice_ref: Invoice reference string (e.g., "INV-ABC123")
            lines: List of line item dicts with product_id, quantity, unit_price
            is_expense: True if expense/purchase, False if revenue/sale
            
        Returns:
            List of StockMovement records created
        """
        movements = []
        
        for line in lines:
            product_id = line.get("product_id")
            if not product_id:
                continue  # Skip lines without linked products
                
            quantity = line.get("quantity", 1)
            unit_price = Decimal(str(line.get("unit_price", 0)))
            invoice_line_id = line.get("id")  # If available
            
            try:
                if is_expense:
                    # Purchases add stock
                    movement = self.record_purchase(
                        product_id=product_id,
                        quantity=quantity,
                        unit_cost=unit_price,
                        expense_id=invoice_id,
                        reference_id=invoice_ref,
                    )
                else:
                    # Sales deduct stock
                    movement = self.record_sale(
                        product_id=product_id,
                        quantity=quantity,
                        unit_price=unit_price,
                        invoice_line_id=invoice_line_id,
                        reference_id=invoice_ref,
                    )
                    
                if movement:
                    movements.append(movement)
                    
            except ValueError as e:
                logger.warning(f"Inventory processing error for product {product_id}: {e}")
                # Continue processing other lines even if one fails
                
        return movements

    def get_cogs_for_period(
        self,
        start_date,
        end_date,
    ) -> dict:
        """
        Calculate Cost of Goods Sold (COGS) for a period.
        
        COGS = Beginning Inventory + Purchases - Ending Inventory
        
        This is used by the tax reporting service for accurate profit calculation.
        
        Args:
            start_date: Start of the period
            end_date: End of the period
            
        Returns:
            dict with cogs_amount, purchases_amount, beginning_inventory, ending_inventory
        """
        from sqlalchemy import and_
        
        # Get all SALE movements in period (this is our COGS at selling price)
        sales_query = self._db.query(
            func.sum(StockMovement.total_cost)
        ).filter(
            StockMovement.user_id == self._user_id,
            StockMovement.movement_type == StockMovementType.SALE,
            StockMovement.created_at >= start_date,
            StockMovement.created_at <= end_date,
        )
        
        # Get total cost of goods sold (using unit_cost from movement)
        cogs_at_cost = self._db.query(
            func.sum(
                func.abs(StockMovement.quantity) * 
                func.coalesce(StockMovement.unit_cost, Decimal(0))
            )
        ).filter(
            StockMovement.user_id == self._user_id,
            StockMovement.movement_type == StockMovementType.SALE,
            StockMovement.created_at >= start_date,
            StockMovement.created_at <= end_date,
        ).scalar() or Decimal(0)
        
        # Get purchases in period
        purchases_amount = self._db.query(
            func.sum(StockMovement.total_cost)
        ).filter(
            StockMovement.user_id == self._user_id,
            StockMovement.movement_type == StockMovementType.PURCHASE,
            StockMovement.created_at >= start_date,
            StockMovement.created_at <= end_date,
        ).scalar() or Decimal(0)
        
        # Current inventory value
        current_inventory = self.get_inventory_summary().total_stock_value
        
        return {
            "cogs_amount": cogs_at_cost,
            "purchases_amount": purchases_amount,
            "current_inventory_value": current_inventory,
            "period_start": start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),
            "period_end": end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date),
        }

    def list_movements(
        self,
        product_id: int | None = None,
        movement_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[Sequence[StockMovement], int]:
        """List stock movements with filtering."""
        query = self._db.query(StockMovement).options(
            joinedload(StockMovement.product)
        ).filter(StockMovement.user_id == self._user_id)

        if product_id:
            query = query.filter(StockMovement.product_id == product_id)

        if movement_type:
            query = query.filter(StockMovement.movement_type == StockMovementType(movement_type))

        total = query.count()
        offset = (page - 1) * page_size
        movements = query.order_by(StockMovement.created_at.desc()).offset(offset).limit(page_size).all()

        return movements, total

    # ========================================================================
    # Supplier Operations
    # ========================================================================

    def create_supplier(self, data: SupplierCreate) -> Supplier:
        """Create a new supplier."""
        supplier = Supplier(
            user_id=self._user_id,
            name=data.name,
            contact_name=data.contact_name,
            email=data.email,
            phone=data.phone,
            address=data.address,
            notes=data.notes,
        )
        self._db.add(supplier)
        self._db.commit()
        self._db.refresh(supplier)
        logger.info(f"Created supplier: {supplier.name} (id={supplier.id})")
        return supplier

    def get_supplier(self, supplier_id: int) -> Supplier | None:
        """Get a supplier by ID."""
        return self._db.query(Supplier).filter(
            Supplier.id == supplier_id,
            Supplier.user_id == self._user_id,
        ).first()

    def list_suppliers(self, include_inactive: bool = False) -> Sequence[Supplier]:
        """List all suppliers."""
        query = self._db.query(Supplier).filter(Supplier.user_id == self._user_id)
        if not include_inactive:
            query = query.filter(Supplier.is_active == True)
        return query.order_by(Supplier.name).all()

    def update_supplier(self, supplier_id: int, data: SupplierUpdate) -> Supplier | None:
        """Update a supplier."""
        supplier = self.get_supplier(supplier_id)
        if not supplier:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(supplier, key, value)
        
        self._db.commit()
        self._db.refresh(supplier)
        return supplier

    def delete_supplier(self, supplier_id: int) -> bool:
        """Soft delete a supplier."""
        supplier = self.get_supplier(supplier_id)
        if not supplier:
            return False
        
        supplier.is_active = False
        self._db.commit()
        return True

    # ========================================================================
    # Analytics & Reporting
    # ========================================================================

    def get_inventory_summary(self) -> InventorySummary:
        """Get summary statistics for inventory dashboard."""
        # Total and active products
        total_products = self._db.query(func.count(Product.id)).filter(
            Product.user_id == self._user_id,
        ).scalar() or 0

        active_products = self._db.query(func.count(Product.id)).filter(
            Product.user_id == self._user_id,
            Product.is_active == True,
        ).scalar() or 0

        # Low stock and out of stock counts
        low_stock_count = self._db.query(func.count(Product.id)).filter(
            Product.user_id == self._user_id,
            Product.is_active == True,
            Product.track_stock == True,
            Product.quantity_in_stock <= Product.reorder_level,
            Product.quantity_in_stock > 0,
        ).scalar() or 0

        out_of_stock_count = self._db.query(func.count(Product.id)).filter(
            Product.user_id == self._user_id,
            Product.is_active == True,
            Product.track_stock == True,
            Product.quantity_in_stock <= 0,
        ).scalar() or 0

        # Stock values - using cost_price or selling_price if no cost
        products = self._db.query(Product).filter(
            Product.user_id == self._user_id,
            Product.is_active == True,
            Product.track_stock == True,
        ).all()

        total_stock_value = Decimal("0")
        total_potential_revenue = Decimal("0")
        for p in products:
            total_stock_value += p.stock_value
            total_potential_revenue += p.potential_revenue

        # Categories count
        categories_count = self._db.query(func.count(ProductCategory.id)).filter(
            ProductCategory.user_id == self._user_id,
            ProductCategory.is_active == True,
        ).scalar() or 0

        return InventorySummary(
            total_products=total_products,
            active_products=active_products,
            low_stock_count=low_stock_count,
            out_of_stock_count=out_of_stock_count,
            total_stock_value=total_stock_value,
            total_potential_revenue=total_potential_revenue,
            categories_count=categories_count,
        )

    def get_low_stock_alerts(self) -> list[LowStockAlert]:
        """Get list of products that need restocking."""
        products = self._db.query(Product).filter(
            Product.user_id == self._user_id,
            Product.is_active == True,
            Product.track_stock == True,
            Product.quantity_in_stock <= Product.reorder_level,
        ).order_by(Product.quantity_in_stock).all()

        return [
            LowStockAlert(
                product_id=p.id,
                product_name=p.name,
                sku=p.sku,
                current_stock=p.quantity_in_stock,
                reorder_level=p.reorder_level,
                reorder_quantity=p.reorder_quantity,
                unit=p.unit,
            )
            for p in products
        ]


def build_inventory_service(db: Session, user_id: int) -> InventoryService:
    """Factory function to create an InventoryService instance."""
    return InventoryService(db=db, user_id=user_id)
