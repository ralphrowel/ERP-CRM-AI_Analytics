"""V2.3 schema: Multi-Currency & Foreign Exchange (FX) Engine

Revision ID: 0020_multi_currency_fx
Revises: 0019_gl_audit_defaults
Create Date: 2026-10-13 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_multi_currency_fx"
down_revision: str | None = "0019_gl_audit_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create currencies table
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(3), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column("decimal_places", sa.SmallInteger(), server_default="2", nullable=False),
        sa.Column("is_base", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Create fx_rates table
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "from_currency_code",
            sa.String(3),
            sa.ForeignKey("currencies.code", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "to_currency_code",
            sa.String(3),
            sa.ForeignKey("currencies.code", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("effective_date", sa.Date(), nullable=False, index=True),
        sa.Column("rate", sa.Numeric(19, 6), nullable=False),
        sa.Column("source", sa.String(50), server_default="manual", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("rate > 0", name="ck_fx_rates_rate_positive"),
        sa.UniqueConstraint(
            "from_currency_code",
            "to_currency_code",
            "effective_date",
            name="uq_fx_rates_pair_date",
        ),
    )

    # 3. Seed baseline currencies
    currencies_table = sa.table(
        "currencies",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("symbol", sa.String),
        sa.column("decimal_places", sa.SmallInteger),
        sa.column("is_base", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        currencies_table,
        [
            {
                "code": "PHP",
                "name": "Philippine Peso",
                "symbol": "₱",
                "decimal_places": 2,
                "is_base": True,
                "is_active": True,
            },
            {
                "code": "USD",
                "name": "US Dollar",
                "symbol": "$",
                "decimal_places": 2,
                "is_base": False,
                "is_active": True,
            },
            {
                "code": "EUR",
                "name": "Euro",
                "symbol": "€",
                "decimal_places": 2,
                "is_base": False,
                "is_active": True,
            },
            {
                "code": "SGD",
                "name": "Singapore Dollar",
                "symbol": "S$",
                "decimal_places": 2,
                "is_base": False,
                "is_active": True,
            },
            {
                "code": "JPY",
                "name": "Japanese Yen",
                "symbol": "¥",
                "decimal_places": 0,
                "is_base": False,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("fx_rates")
    op.drop_table("currencies")
