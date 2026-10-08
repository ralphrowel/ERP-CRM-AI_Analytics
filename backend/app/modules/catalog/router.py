from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.catalog.models import Product, ProductCategory
from app.modules.catalog.schemas import (
    PaginatedProductsResponse,
    ProductCategoryCreate,
    ProductCategoryResponse,
    ProductCategoryUpdate,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.modules.catalog.service import CatalogService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User

router = APIRouter(prefix="", tags=["Catalog"])


def get_catalog_service(db: Annotated[Session, Depends(get_db)]) -> CatalogService:
    return CatalogService(db)


# --- Product Categories ---
@router.get("/product-categories", response_model=list[ProductCategoryResponse])
def list_categories(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    include_inactive: bool = Query(False),
) -> list[ProductCategory]:
    return service.list_categories(include_inactive=include_inactive)


@router.post(
    "/product-categories",
    response_model=ProductCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    payload: ProductCategoryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductCategory:
    return service.create_category(payload, creator_id=current_user.id)


@router.patch("/product-categories/{category_id}", response_model=ProductCategoryResponse)
def update_category(
    category_id: int,
    payload: ProductCategoryUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ProductCategory:
    return service.update_category(category_id, payload, updater_id=current_user.id)


# --- Products ---
@router.get("/products", response_model=PaginatedProductsResponse)
def list_products(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    category_id: int | None = Query(None),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedProductsResponse:
    products, total = service.list_products(
        page=page,
        page_size=page_size,
        category_id=category_id,
        search=search,
        is_active=is_active,
    )
    return PaginatedProductsResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    return service.get_product(product_id)


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    return service.create_product(payload, creator_id=current_user.id)


@router.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    return service.update_product(product_id, payload, updater_id=current_user.id)


@router.post("/products/{product_id}/deactivate", response_model=ProductResponse)
def deactivate_product(
    product_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    return service.deactivate_product(product_id, updater_id=current_user.id)
