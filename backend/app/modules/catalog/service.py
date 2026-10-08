from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.errors import AppException, ConflictException, NotFoundException
from app.core.money import round_unit_price
from app.modules.catalog.models import Product, ProductCategory
from app.modules.catalog.schemas import (
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductCreate,
    ProductUpdate,
)


class CatalogService:
    def __init__(self, db: Session, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or get_clock()

    # --- Categories ---
    def list_categories(self, include_inactive: bool = False) -> list[ProductCategory]:
        stmt = select(ProductCategory).order_by(ProductCategory.name.asc())
        if not include_inactive:
            stmt = stmt.where(ProductCategory.is_active.is_(True))
        return list(self.db.execute(stmt).scalars().all())

    def create_category(
        self, data: ProductCategoryCreate, creator_id: int | None = None
    ) -> ProductCategory:
        name_clean = data.name.strip()
        existing = self.db.execute(
            select(ProductCategory).where(func.lower(ProductCategory.name) == name_clean.lower())
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                status_code=400,
                code="CATEGORY_NAME_EXISTS",
                title="Bad Request",
                detail=f"Category '{name_clean}' already exists.",
            )

        cat = ProductCategory(
            name=name_clean,
            parent_id=data.parent_id,
            is_active=True,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(cat)
        self.db.commit()
        self.db.refresh(cat)
        return cat

    def update_category(
        self, category_id: int, data: ProductCategoryUpdate, updater_id: int | None = None
    ) -> ProductCategory:
        cat = self.db.get(ProductCategory, category_id)
        if not cat:
            raise NotFoundException(detail="Category not found.")

        if data.name is not None:
            name_clean = data.name.strip()
            existing = self.db.execute(
                select(ProductCategory).where(
                    func.lower(ProductCategory.name) == name_clean.lower(),
                    ProductCategory.id != category_id,
                )
            ).scalar_one_or_none()
            if existing:
                raise AppException(
                    status_code=400,
                    code="CATEGORY_NAME_EXISTS",
                    title="Bad Request",
                    detail=f"Category '{name_clean}' already exists.",
                )
            cat.name = name_clean

        if data.parent_id is not None:
            if data.parent_id == category_id:
                raise AppException(
                    status_code=400,
                    code="INVALID_PARENT_CATEGORY",
                    title="Bad Request",
                    detail="A category cannot be its own parent.",
                )
            cat.parent_id = data.parent_id

        if data.is_active is not None:
            cat.is_active = data.is_active

        cat.updated_by = updater_id
        self.db.commit()
        self.db.refresh(cat)
        return cat

    # --- Products ---
    def list_products(
        self,
        page: int = 1,
        page_size: int = 25,
        category_id: int | None = None,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Product], int]:
        stmt = select(Product)
        count_stmt = select(func.count(Product.id))

        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
            count_stmt = count_stmt.where(Product.category_id == category_id)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
            count_stmt = count_stmt.where(Product.is_active == is_active)
        if search:
            search_pattern = f"%{search.strip()}%"
            term_clause = or_(
                Product.name.ilike(search_pattern),
                Product.sku.ilike(search_pattern),
            )
            stmt = stmt.where(term_clause)
            count_stmt = count_stmt.where(term_clause)

        total = self.db.execute(count_stmt).scalar_one()
        offset = (page - 1) * page_size
        products = (
            self.db.execute(stmt.order_by(Product.id.asc()).offset(offset).limit(page_size))
            .scalars()
            .all()
        )
        return list(products), total

    def get_product(self, product_id: int) -> Product:
        prod = self.db.get(Product, product_id)
        if not prod:
            raise NotFoundException(detail="Product not found.")
        return prod

    def create_product(self, data: ProductCreate, creator_id: int | None = None) -> Product:
        sku_clean = data.sku.strip().upper()
        existing = self.db.execute(
            select(Product).where(Product.sku == sku_clean)
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                status_code=400,
                code="SKU_ALREADY_EXISTS",
                title="Bad Request",
                detail=f"Product with SKU '{sku_clean}' already exists.",
            )

        if data.category_id:
            cat = self.db.get(ProductCategory, data.category_id)
            if not cat or not cat.is_active:
                raise AppException(
                    status_code=400,
                    code="INVALID_CATEGORY",
                    title="Bad Request",
                    detail="Specified product category does not exist or is inactive.",
                )

        prod = Product(
            sku=sku_clean,
            name=data.name.strip(),
            description=data.description.strip() if data.description else None,
            category_id=data.category_id,
            product_type=data.product_type,
            uom=data.uom,
            list_price=round_unit_price(data.list_price),
            is_active=True,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(prod)
        self.db.commit()
        self.db.refresh(prod)
        return prod

    def update_product(
        self, product_id: int, data: ProductUpdate, updater_id: int | None = None
    ) -> Product:
        prod = self.get_product(product_id)

        # Optimistic locking check (§4.1)
        if prod.version != data.version:
            raise ConflictException(
                detail="Product record was modified by another transaction. Please reload."
            )

        if data.sku is not None:
            sku_clean = data.sku.strip().upper()
            if sku_clean != prod.sku:
                existing = self.db.execute(
                    select(Product).where(
                        Product.sku == sku_clean,
                        Product.id != product_id,
                    )
                ).scalar_one_or_none()
                if existing:
                    raise AppException(
                        status_code=400,
                        code="SKU_ALREADY_EXISTS",
                        title="Bad Request",
                        detail=f"Product with SKU '{sku_clean}' already exists.",
                    )
                prod.sku = sku_clean

        if data.name is not None:
            prod.name = data.name.strip()
        if data.description is not None:
            prod.description = data.description.strip() if data.description else None
        if data.category_id is not None:
            cat = self.db.get(ProductCategory, data.category_id)
            if not cat or not cat.is_active:
                raise AppException(
                    status_code=400,
                    code="INVALID_CATEGORY",
                    title="Bad Request",
                    detail="Specified category does not exist or is inactive.",
                )
            prod.category_id = data.category_id
        if data.product_type is not None:
            prod.product_type = data.product_type
        if data.uom is not None:
            prod.uom = data.uom
        if data.list_price is not None:
            prod.list_price = round_unit_price(data.list_price)
        if data.is_active is not None:
            prod.is_active = data.is_active

        prod.version += 1
        prod.updated_by = updater_id
        self.db.commit()
        self.db.refresh(prod)
        return prod

    def deactivate_product(self, product_id: int, updater_id: int | None = None) -> Product:
        prod = self.get_product(product_id)
        prod.is_active = False
        prod.version += 1
        prod.updated_by = updater_id
        self.db.commit()
        self.db.refresh(prod)
        return prod
