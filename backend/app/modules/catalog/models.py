from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import AuditMixin, Base, VersionMixin


class ProductCategory(Base, AuditMixin):
    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")
    parent: Mapped["ProductCategory | None"] = relationship("ProductCategory", remote_side=[id])


class Product(Base, AuditMixin, VersionMixin):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("product_type IN ('stock', 'service')", name="ck_products_type"),
        CheckConstraint(
            "uom IN ('pc', 'box', 'pack', 'kg', 'l', 'm', 'hr')",
            name="ck_products_uom",
        ),
        CheckConstraint("list_price >= 0", name="ck_products_list_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_type: Mapped[str] = mapped_column(String(20), nullable=False, default="stock")
    uom: Mapped[str] = mapped_column(String(20), nullable=False, default="pc")
    list_price: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0.0000")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped[ProductCategory | None] = relationship(
        "ProductCategory", back_populates="products"
    )
