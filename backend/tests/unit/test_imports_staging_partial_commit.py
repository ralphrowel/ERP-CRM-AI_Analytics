"""
Unit and integration tests for Milestone V1.0:
Legacy Dirty-Data Import Engine & Operational Core Staging Pipeline.

Validates:
1. Ingestion of 1,000-row dirty CSV into raw TEXT staging tables.
2. Row-level validation engine flagging syntax, numeric, email, and enum defects.
3. Partial commits: commits valid rows via domain services while leaving invalid rows in staging.
4. Product and Contact staging and import workflows.
5. Legacy dirty-data generator (Path B) reproducibility and defect manifest ground truth.
6. HTTP REST API endpoints (/api/v1/imports/...).
"""

import csv
import io
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.modules.catalog.models import Product
from app.modules.crm.models import Contact, Customer
from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole
from app.modules.identity.service import IdentityService
from app.modules.imports.models import ImportStagingCustomer
from app.modules.imports.service import ImportService
from app.modules.sales.models import TaxRate
from simulator.legacy_generator import LegacyDataGenerator


@pytest.fixture
def import_setup(db_session: Session):
    """Seed tax rate, superuser/admin, and permissions for import testing."""
    # Ensure default TaxRate
    tax_rate = db_session.execute(select(TaxRate).limit(1)).scalar_one_or_none()
    if not tax_rate:
        tax_rate = TaxRate(
            code="VAT12",
            name="Value Added Tax 12%",
            rate=Decimal("0.1200"),
            is_active=True,
            is_default=True,
        )
        db_session.add(tax_rate)
        db_session.flush()

    # Permissions
    perm_upload = db_session.execute(
        select(Permission).where(Permission.code == "import:upload")
    ).scalar_one_or_none()
    if not perm_upload:
        perm_upload = Permission(
            code="import:upload", description="Upload CSV", module="imports"
        )
        db_session.add(perm_upload)

    perm_commit = db_session.execute(
        select(Permission).where(Permission.code == "import:commit")
    ).scalar_one_or_none()
    if not perm_commit:
        perm_commit = Permission(
            code="import:commit", description="Commit imports", module="imports"
        )
        db_session.add(perm_commit)

    perm_read = db_session.execute(
        select(Permission).where(Permission.code == "import:read")
    ).scalar_one_or_none()
    if not perm_read:
        perm_read = Permission(
            code="import:read", description="Read imports", module="imports"
        )
        db_session.add(perm_read)
    db_session.flush()

    # Admin Role
    admin_role = db_session.execute(
        select(Role).where(Role.code == "admin")
    ).scalar_one_or_none()
    if not admin_role:
        admin_role = Role(code="admin", name="Administrator")
        db_session.add(admin_role)
        db_session.flush()

    for p in [perm_upload, perm_commit, perm_read]:
        rp_exists = db_session.execute(
            select(RolePermission).where(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_id == p.id,
            )
        ).scalar_one_or_none()
        if not rp_exists:
            db_session.add(
                RolePermission(role_id=admin_role.id, permission_id=p.id, scope="all")
            )

    # Test Admin User
    admin_user = db_session.execute(
        select(User).where(User.email == "import_admin@corp.local")
    ).scalar_one_or_none()
    if not admin_user:
        admin_user = User(
            email="import_admin@corp.local",
            password_hash=hash_password("AdminPass123!"),
            full_name="Import Admin",
            is_superuser=True,
            is_active=True,
        )
        db_session.add(admin_user)
        db_session.flush()
        db_session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))

    db_session.commit()
    return {"admin_user": admin_user, "tax_rate": tax_rate}


def test_dirty_customer_csv_1000_rows_partial_commit(
    db_session: Session, import_setup: dict
):
    """
    Exit Criteria 1:
    Importing a 1,000-row dirty customer CSV commits the valid rows and
    shows row-level errors for the rest.
    """
    service = ImportService(db_session)
    user = import_setup["admin_user"]

    # Generate 1,000 rows: 750 valid, 250 dirty
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "name",
            "email",
            "phone",
            "tin",
            "city",
            "province",
            "customer_type",
            "payment_terms",
            "credit_limit",
        ],
    )
    writer.writeheader()

    expected_valid = 0
    expected_error = 0

    for i in range(1, 1001):
        if i % 4 == 1:
            # Error 1: Missing Name
            writer.writerow(
                {
                    "name": "",
                    "email": f"client{i}@example.ph",
                    "phone": "09171234567",
                    "tin": "123-456-789-000",
                    "city": "Manila",
                    "province": "Metro Manila",
                    "customer_type": "company",
                    "payment_terms": "30",
                    "credit_limit": "50000",
                }
            )
            expected_error += 1
        elif i % 4 == 2:
            # Error 2: Malformed Email
            writer.writerow(
                {
                    "name": f"Defective Email Corp {i}",
                    "email": "not-an-email",
                    "phone": "09171234567",
                    "tin": "123-456-789-000",
                    "city": "Quezon City",
                    "province": "Metro Manila",
                    "customer_type": "company",
                    "payment_terms": "30",
                    "credit_limit": "50000",
                }
            )
            expected_error += 1
        elif i % 20 == 0:
            # Error 3: Negative Credit Limit
            writer.writerow(
                {
                    "name": f"Negative Limit Corp {i}",
                    "email": f"negative{i}@example.ph",
                    "phone": "09171234567",
                    "tin": "123-456-789-000",
                    "city": "Makati",
                    "province": "Metro Manila",
                    "customer_type": "company",
                    "payment_terms": "30",
                    "credit_limit": "-15000.00",
                }
            )
            expected_error += 1
        else:
            # Valid Row (with Philippine currency symbols and commas)
            writer.writerow(
                {
                    "name": f"Enterprise Customer {i} Ltd.",
                    "email": f"valid{i}@corp-manila.ph",
                    "phone": f"0917{1000000 + i}",
                    "tin": f"999-{i:03d}-111-000",
                    "city": "Taguig",
                    "province": "Metro Manila",
                    "customer_type": "company" if i % 2 == 0 else "individual",
                    "payment_terms": "30",
                    "credit_limit": f"₱ {50000 + i:,.2f}",
                }
            )
            expected_valid += 1

    csv_bytes = buffer.getvalue().encode("utf-8")

    # Ingest 1,000 rows
    batch = service.upload_csv(
        file_name="dirty_customers_1000.csv",
        file_bytes=csv_bytes,
        entity_type="customer",
        user_id=user.id,
        source_label="unit_test",
    )

    assert batch.row_count == 1000
    assert batch.valid_count == expected_valid
    assert batch.error_count == expected_error
    assert batch.status == "validated"

    # Verify staging records are preserved as raw text
    staging_rows = (
        db_session.execute(
            select(ImportStagingCustomer).where(ImportStagingCustomer.batch_id == batch.id)
        )
        .scalars()
        .all()
    )
    assert len(staging_rows) == 1000

    # Inspect error records
    errors_sample = [r for r in staging_rows if r.validation_errors is not None]
    assert len(errors_sample) == expected_error
    assert all("field" in r.validation_errors[0] for r in errors_sample)

    # Partial Commit Execution
    committed_batch = service.commit_batch(batch.id, user_id=user.id)

    assert committed_batch.status == "committed"
    assert committed_batch.committed_count == expected_valid
    assert committed_batch.error_count == expected_error
    assert committed_batch.committed_at is not None

    # Verify committed customers in operational database
    committed_customers_count = db_session.execute(
        select(Customer).where(Customer.name.like("Enterprise Customer %"))
    ).scalars().all()
    assert len(committed_customers_count) == expected_valid

    # Verify defective rows stayed uncommitted in staging with validation_errors
    retained_staging_errors = (
        db_session.execute(
            select(ImportStagingCustomer).where(
                ImportStagingCustomer.batch_id == batch.id,
                ImportStagingCustomer.committed_customer_id.is_(None),
            )
        )
        .scalars()
        .all()
    )
    assert len(retained_staging_errors) == expected_error


def test_product_and_contact_csv_import_staging(
    db_session: Session, import_setup: dict
):
    """
    Validates product and contact staging pipelines, duplicate detection,
    and partial commits.
    """
    service = ImportService(db_session)
    user = import_setup["admin_user"]

    # 1. Product Staging Import
    product_csv = (
        "sku,name,product_type,uom,list_price\n"
        'SKU-GOOD-01,Valid Product 1,stock,pc,"₱ 1,500.00"\n'
        "SKU-GOOD-02,Valid Product 2,service,hr,500.00\n"
        "SKU-GOOD-01,Duplicate SKU,stock,pc,250.00\n"  # Duplicate in batch
        "SKU-BAD-03,Invalid Price,stock,pc,-50.00\n"   # Negative price
    )

    batch_prod = service.upload_csv(
        file_name="products.csv",
        file_bytes=product_csv.encode("utf-8"),
        entity_type="product",
        user_id=user.id,
    )

    assert batch_prod.row_count == 4
    assert batch_prod.valid_count == 2
    assert batch_prod.error_count == 2

    # Commit valid products
    committed_prod = service.commit_batch(batch_prod.id, user_id=user.id)
    assert committed_prod.committed_count == 2

    created_prod1 = db_session.execute(
        select(Product).where(Product.sku == "SKU-GOOD-01")
    ).scalar_one_or_none()
    assert created_prod1 is not None
    assert created_prod1.list_price == Decimal("1500.0000")

    # 2. Contact Staging Import
    # Create customer first
    from app.modules.crm.schemas import CustomerCreate
    cust = service.crm_service.create_customer(
        CustomerCreate(name="Contact Target Company", customer_type="company", status="active")
    )

    contact_csv = (
        f"customer_id,first_name,last_name,email,job_title\n"
        f"{cust.customer_no},Juan,Dela Cruz,juan@target.ph,Procurement Lead\n"
        f"{cust.id},Maria,Clara,maria@target.ph,Finance Officer\n"
        f"NON_EXISTENT_CUST,Ghost,User,ghost@example.ph,Unknown\n"
    )

    batch_contact = service.upload_csv(
        file_name="contacts.csv",
        file_bytes=contact_csv.encode("utf-8"),
        entity_type="contact",
        user_id=user.id,
    )

    assert batch_contact.row_count == 3
    assert batch_contact.valid_count == 2
    assert batch_contact.error_count == 1

    committed_contact = service.commit_batch(batch_contact.id, user_id=user.id)
    assert committed_contact.committed_count == 2

    contacts = db_session.execute(
        select(Contact).where(Contact.customer_id == cust.id)
    ).scalars().all()
    assert len(contacts) == 2


def test_legacy_generator_defect_manifest_reproducibility(tmp_path: Path):
    """
    Exit Criteria 3:
    Legacy CSVs + defect manifest are generated reproducibly with controlled defects.
    """
    gen1 = LegacyDataGenerator(seed=7, out_dir=tmp_path / "run1")
    res1 = gen1.run(customer_count=50, sales_count=200)

    gen2 = LegacyDataGenerator(seed=7, out_dir=tmp_path / "run2")
    res2 = gen2.run(customer_count=50, sales_count=200)

    assert res1["total_defects"] == res2["total_defects"]
    assert res1["defects_by_type"] == res2["defects_by_type"]

    # Manifest file exists and is populated
    manifest_path = Path(res1["manifest_path"])
    assert manifest_path.exists()
    assert manifest_path.stat().st_size > 0

    customers_csv = Path(res1["customers_path"])
    assert customers_csv.exists()
    assert customers_csv.stat().st_size > 0

    sales_csv = Path(res1["sales_path"])
    assert sales_csv.exists()
    assert sales_csv.stat().st_size > 0


def test_import_http_api_endpoints(db_session: Session, import_setup: dict):
    """
    Validates REST API endpoints for import upload-raw, batch list, batch details, and commit.
    """
    identity_svc = IdentityService(db_session)
    _, token, _ = identity_svc.authenticate_user("import_admin@corp.local", "AdminPass123!")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Upload Raw CSV
        csv_payload = {
            "entity_type": "customer",
            "file_name": "api_test_customers.csv",
            "csv_content": (
                "name,email,customer_type,payment_terms,credit_limit\n"
                "Acme Global,acme@global.ph,company,30,500000\n"
                "Beta Logistics,beta@logistics.ph,company,15,250000\n"
            ),
            "source_label": "api_test",
        }
        res_upload = client.post("/api/v1/imports/upload-raw", json=csv_payload, headers=headers)
        assert res_upload.status_code == 201
        batch_data = res_upload.json()
        batch_id = batch_data["id"]
        assert batch_data["row_count"] == 2
        assert batch_data["valid_count"] == 2

        # 2. List Batches
        res_list = client.get("/api/v1/imports/batches", headers=headers)
        assert res_list.status_code == 200
        assert len(res_list.json()) >= 1

        # 3. Get Batch Details
        res_detail = client.get(f"/api/v1/imports/batches/{batch_id}", headers=headers)
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["batch"]["id"] == batch_id
        assert len(detail_data["staging_rows"]) == 2

        # 4. Commit Batch
        res_commit = client.post(f"/api/v1/imports/batches/{batch_id}/commit", headers=headers)
        assert res_commit.status_code == 200
        commit_data = res_commit.json()
        assert commit_data["committed_count"] == 2
        assert commit_data["status"] == "committed"

    finally:
        app.dependency_overrides.clear()
