import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base
from app.core.numbering import DocumentSequence  # noqa: F401
from app.core.status_history import StatusHistory  # noqa: F401
from app.modules.catalog.models import Product, ProductCategory  # noqa: F401
from app.modules.crm.models import (  # noqa: F401
    Activity,
    Contact,
    Customer,
    CustomerAddress,
    Lead,
    Opportunity,
)
from app.modules.identity.models import User, UserSession  # noqa: F401
from app.modules.inventory.models import (  # noqa: F401
    InventoryBalance,
    InventoryTransaction,
    StockReservation,
    Warehouse,
)
from app.modules.organization.models import CompanySettings, Department, Employee  # noqa: F401
from app.modules.sales.models import (  # noqa: F401
    CreditNote,
    CreditNoteItem,
    IdempotencyKey,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAllocation,
    Quote,
    QuoteItem,
    SalesOrder,
    SalesOrderItem,
    TaxRate,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Use migration connection URL (runs as erp_owner)
db_url = os.getenv("MIGRATION_DATABASE_URL") or settings.MIGRATION_DATABASE_URL
config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
