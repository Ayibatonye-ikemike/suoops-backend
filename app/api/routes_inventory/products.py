"""Product endpoints."""
import logging

from fastapi import APIRouter, HTTPException, Query

from app.models import inventory_schemas as schemas
from .dependencies import InventoryServiceDep, InventoryServiceAdminDep
from .helpers import product_to_out

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/products", response_model=schemas.ProductOut, status_code=201)
def create_product(
    data: schemas.ProductCreate,
    service: InventoryServiceAdminDep,
):
    """Create a new product."""
    try:
        product = service.create_product(data)
        return product_to_out(product)
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
        products=[product_to_out(p) for p in products],
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
    return product_to_out(product)


@router.get("/products/sku/{sku}", response_model=schemas.ProductOut)
def get_product_by_sku(
    sku: str,
    service: InventoryServiceDep,
):
    """Get a product by SKU."""
    product = service.get_product_by_sku(sku)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_to_out(product)


@router.get("/products/barcode/{barcode}", response_model=schemas.ProductOut)
def get_product_by_barcode(
    barcode: str,
    service: InventoryServiceDep,
):
    """Get a product by barcode (for barcode scanner integration)."""
    product = service.get_product_by_barcode(barcode)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_to_out(product)


@router.patch("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    data: schemas.ProductUpdate,
    service: InventoryServiceAdminDep,
):
    """Update a product."""
    try:
        product = service.update_product(product_id, data)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return product_to_out(product)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    service: InventoryServiceAdminDep,
):
    """Delete a product (soft delete)."""
    if not service.delete_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
