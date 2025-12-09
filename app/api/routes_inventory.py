"""
Inventory API Routes.

RESTful endpoints for inventory management:
- Products (CRUD, search, stock levels)
- Categories (CRUD)
- Stock Movements (adjustments, history)
- Suppliers (CRUD)
- Analytics (summary, alerts)
"""
from typing import Annotated, TypeAlias
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models import inventory_schemas as schemas
from app.services.inventory_service import build_inventory_service, InventoryService

router = APIRouter()
logger = logging.getLogger(__name__)

CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
DbDep: TypeAlias = Annotated[Session, Depends(get_db)]


def get_inventory_service(current_user_id: CurrentUserDep, db: DbDep) -> InventoryService:
    """Get InventoryService for the requesting user."""
    return build_inventory_service(db, user_id=current_user_id)


InventoryServiceDep: TypeAlias = Annotated[InventoryService, Depends(get_inventory_service)]


# ============================================================================
# Product Category Endpoints
# ============================================================================

@router.post("/categories", response_model=schemas.ProductCategoryOut, status_code=201)
def create_category(
    data: schemas.ProductCategoryCreate,
    service: InventoryServiceDep,
):
    """Create a new product category."""
    category = service.create_category(data)
    return schemas.ProductCategoryOut(
        id=category.id,
        name=category.name,
        description=category.description,
        color=category.color,
        is_active=category.is_active,
        product_count=len(category.products) if category.products else 0,
    )


@router.get("/categories", response_model=list[schemas.ProductCategoryOut])
def list_categories(
    service: InventoryServiceDep,
    include_inactive: bool = Query(False, description="Include inactive categories"),
):
    """List all product categories."""
    categories = service.list_categories(include_inactive=include_inactive)
    return [
        schemas.ProductCategoryOut(
            id=c.id,
            name=c.name,
            description=c.description,
            color=c.color,
            is_active=c.is_active,
            product_count=len(c.products) if c.products else 0,
        )
        for c in categories
    ]


@router.get("/categories/{category_id}", response_model=schemas.ProductCategoryOut)
def get_category(
    category_id: int,
    service: InventoryServiceDep,
):
    """Get a category by ID."""
    category = service.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return schemas.ProductCategoryOut(
        id=category.id,
        name=category.name,
        description=category.description,
        color=category.color,
        is_active=category.is_active,
        product_count=len(category.products) if category.products else 0,
    )


@router.patch("/categories/{category_id}", response_model=schemas.ProductCategoryOut)
def update_category(
    category_id: int,
    data: schemas.ProductCategoryUpdate,
    service: InventoryServiceDep,
):
    """Update a category."""
    category = service.update_category(category_id, data)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return schemas.ProductCategoryOut(
        id=category.id,
        name=category.name,
        description=category.description,
        color=category.color,
        is_active=category.is_active,
        product_count=len(category.products) if category.products else 0,
    )


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    service: InventoryServiceDep,
):
    """Delete a category (soft delete)."""
    if not service.delete_category(category_id):
        raise HTTPException(status_code=404, detail="Category not found")


# ============================================================================
# Product Endpoints
# ============================================================================

@router.post("/products", response_model=schemas.ProductOut, status_code=201)
def create_product(
    data: schemas.ProductCreate,
    service: InventoryServiceDep,
):
    """Create a new product."""
    try:
        product = service.create_product(data)
        return _product_to_out(product)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/products", response_model=schemas.ProductListOut)
def list_products(
    service: InventoryServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category_id: int | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search by name, SKU, or barcode"),
    include_inactive: bool = Query(False, description="Include inactive products"),
    low_stock_only: bool = Query(False, description="Show only low stock products"),
    out_of_stock_only: bool = Query(False, description="Show only out of stock products"),
):
    """List products with filtering and pagination."""
    products, total = service.list_products(
        page=page,
        page_size=page_size,
        category_id=category_id,
        search=search,
        include_inactive=include_inactive,
        low_stock_only=low_stock_only,
        out_of_stock_only=out_of_stock_only,
    )
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return schemas.ProductListOut(
        products=[_product_to_out(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/products/{product_id}", response_model=schemas.ProductOut)
def get_product(
    product_id: int,
    service: InventoryServiceDep,
):
    """Get a product by ID."""
    product = service.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_out(product)


@router.get("/products/sku/{sku}", response_model=schemas.ProductOut)
def get_product_by_sku(
    sku: str,
    service: InventoryServiceDep,
):
    """Get a product by SKU."""
    product = service.get_product_by_sku(sku)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_out(product)


@router.get("/products/barcode/{barcode}", response_model=schemas.ProductOut)
def get_product_by_barcode(
    barcode: str,
    service: InventoryServiceDep,
):
    """Get a product by barcode (for barcode scanner integration)."""
    product = service.get_product_by_barcode(barcode)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_out(product)


@router.patch("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    data: schemas.ProductUpdate,
    service: InventoryServiceDep,
):
    """Update a product."""
    try:
        product = service.update_product(product_id, data)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return _product_to_out(product)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    service: InventoryServiceDep,
):
    """Delete a product (soft delete)."""
    if not service.delete_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")


# ============================================================================
# Stock Movement Endpoints
# ============================================================================

@router.post("/stock/adjust", response_model=schemas.StockMovementOut, status_code=201)
def adjust_stock(
    data: schemas.StockAdjustmentCreate,
    service: InventoryServiceDep,
):
    """
    Adjust stock for a product.
    
    Use positive quantity to add stock (purchase, return), 
    negative to remove (damage, adjustment).
    """
    try:
        movement = service.adjust_stock(data, created_by="user")
        return _movement_to_out(movement)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stock/movements", response_model=schemas.StockMovementListOut)
def list_stock_movements(
    service: InventoryServiceDep,
    product_id: int | None = Query(None, description="Filter by product"),
    movement_type: str | None = Query(None, description="Filter by movement type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List stock movements (audit trail)."""
    movements, total = service.list_movements(
        product_id=product_id,
        movement_type=movement_type,
        page=page,
        page_size=page_size,
    )
    return schemas.StockMovementListOut(
        movements=[_movement_to_out(m) for m in movements],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================================
# Supplier Endpoints
# ============================================================================

@router.post("/suppliers", response_model=schemas.SupplierOut, status_code=201)
def create_supplier(
    data: schemas.SupplierCreate,
    service: InventoryServiceDep,
):
    """Create a new supplier."""
    supplier = service.create_supplier(data)
    return schemas.SupplierOut.model_validate(supplier)


@router.get("/suppliers", response_model=list[schemas.SupplierOut])
def list_suppliers(
    service: InventoryServiceDep,
    include_inactive: bool = Query(False),
):
    """List all suppliers."""
    suppliers = service.list_suppliers(include_inactive=include_inactive)
    return [schemas.SupplierOut.model_validate(s) for s in suppliers]


@router.get("/suppliers/{supplier_id}", response_model=schemas.SupplierOut)
def get_supplier(
    supplier_id: int,
    service: InventoryServiceDep,
):
    """Get a supplier by ID."""
    supplier = service.get_supplier(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return schemas.SupplierOut.model_validate(supplier)


@router.patch("/suppliers/{supplier_id}", response_model=schemas.SupplierOut)
def update_supplier(
    supplier_id: int,
    data: schemas.SupplierUpdate,
    service: InventoryServiceDep,
):
    """Update a supplier."""
    supplier = service.update_supplier(supplier_id, data)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return schemas.SupplierOut.model_validate(supplier)


@router.delete("/suppliers/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: int,
    service: InventoryServiceDep,
):
    """Delete a supplier (soft delete)."""
    if not service.delete_supplier(supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found")


# ============================================================================
# Analytics Endpoints
# ============================================================================

@router.get("/analytics/summary", response_model=schemas.InventorySummary)
def get_inventory_summary(
    service: InventoryServiceDep,
):
    """Get inventory summary statistics for dashboard."""
    return service.get_inventory_summary()


@router.get("/analytics/low-stock", response_model=list[schemas.LowStockAlert])
def get_low_stock_alerts(
    service: InventoryServiceDep,
):
    """Get products that need restocking."""
    return service.get_low_stock_alerts()


# ============================================================================
# Helper Functions
# ============================================================================

def _product_to_out(product) -> schemas.ProductOut:
    """Convert Product model to ProductOut schema."""
    return schemas.ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        barcode=product.barcode,
        category_id=product.category_id,
        category_name=product.category.name if product.category else None,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        quantity_in_stock=product.quantity_in_stock,
        reorder_level=product.reorder_level,
        reorder_quantity=product.reorder_quantity,
        unit=product.unit,
        is_active=product.is_active,
        track_stock=product.track_stock,
        image_url=product.image_url,
        is_low_stock=product.is_low_stock,
        is_out_of_stock=product.is_out_of_stock,
        stock_value=product.stock_value,
        profit_margin=product.profit_margin,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _movement_to_out(movement) -> schemas.StockMovementOut:
    """Convert StockMovement model to StockMovementOut schema."""
    return schemas.StockMovementOut(
        id=movement.id,
        product_id=movement.product_id,
        product_name=movement.product.name if movement.product else None,
        product_sku=movement.product.sku if movement.product else None,
        movement_type=movement.movement_type.value,
        quantity=movement.quantity,
        quantity_before=movement.quantity_before,
        quantity_after=movement.quantity_after,
        unit_cost=movement.unit_cost,
        total_cost=movement.total_cost,
        reference_type=movement.reference_type,
        reference_id=movement.reference_id,
        reason=movement.reason,
        notes=movement.notes,
        created_at=movement.created_at,
        created_by=movement.created_by,
    )
