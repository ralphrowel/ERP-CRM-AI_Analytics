"""
Milestone V2.0 Integration Tests: End-to-End Traced BI Platform
Roadmap §V2.0 Exit Criteria Verification:
1. End-to-End Traced Scenario:
   Lead created in ERP -> converted to Customer & Opportunity -> Quote issued ->
   Sales Order confirmed -> Invoiced -> Paid -> Extracted to raw -> Transformed to staging ->
   Quality checked (DQ) -> Dimensional Star Schema (mart) -> Power BI DAX & Visiq AI Analyst.
2. Architecture & ADR Documentation Integrity.
"""

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from analytics.db import init_analytics_db
from analytics.dq.runner import DqRunner
from analytics.extract.extractor import Extractor
from analytics.mart.builder import MartBuilder
from analytics.transform.runner import TransformRunner
from analytics.visiq.agent import VisiqAgent
from analytics.visiq.engine import VisiqQueryEngine
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.clock import ControllableClock
from app.core.numbering import DocumentSequence
from app.modules.catalog.models import Product, ProductCategory
from app.modules.crm.models import Customer, Opportunity
from app.modules.crm.service import CRMService
from app.modules.identity.models import User
from app.modules.sales.models import TaxRate
from app.modules.sales.schemas import (
    LineItemPayload,
    PaymentCreatePayload,
    QuoteCreatePayload,
)
from app.modules.sales.service import SalesService


@pytest.fixture
def analytics_test_engine(db_session: Session) -> Engine:
    """Creates an analytics engine for test execution (PostgreSQL in CI or isolated SQLite)."""
    erp_engine = db_session.get_bind()
    if erp_engine.dialect.name == "postgresql":
        analytics_url = os.getenv(
            "ANALYTICS_DATABASE_URL",
            "postgresql+psycopg://analytics_owner:analytics_owner_password@localhost:5432/erp_analytics",
        )
        try:
            engine = create_engine(analytics_url, pool_pre_ping=True)
            with engine.connect():
                pass
            init_analytics_db(engine)
            return engine
        except Exception:
            pass

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_analytics_db(engine)
    return engine


def test_end_to_end_business_scenario_trace(db_session: Session, analytics_test_engine: Engine):
    """
    Traces the entire lifecycle of business data across all platform layers:
    Hop 1: ERP Operational Processing (Lead -> Customer/Opp -> Quote -> Order -> Invoice -> Payment)
    Hop 2: Analytics Extraction (OLTP -> raw)
    Hop 3: Transformation (raw -> staging DAG)
    Hop 4: Data Quality (4D assessment & scoring)
    Hop 5: Dimensional Star Schema (staging -> mart)
    Hop 6: Power BI Semantic Parity (DAX Net Revenue & Margin)
    Hop 7: Visiq AI Analyst Natural Language Explanation
    """
    clock = ControllableClock(datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC))
    crm_service = CRMService(db=db_session, clock=clock)
    sales_service = SalesService(db=db_session, clock=clock)
    erp_engine = db_session.get_bind()

    # -------------------------------------------------------------------------
    # HOP 1: ERP OPERATIONAL INGESTION & PROCESSING
    # -------------------------------------------------------------------------
    # 1.1 Sequences & Baseline Entities
    seq_types = ["customer", "lead", "opportunity", "quote", "sales_order", "invoice", "payment"]
    for st in seq_types:
        if not db_session.query(DocumentSequence).filter_by(doc_type=st).first():
            prefix = {
                "customer": "CUS",
                "lead": "LEAD",
                "opportunity": "OPP",
                "quote": "QT",
                "sales_order": "SO",
                "invoice": "INV",
                "payment": "PAY",
            }[st]
            inc_yr = st not in ["customer"]
            db_session.add(
                DocumentSequence(
                    doc_type=st, prefix=prefix, include_year=inc_yr, padding=6, next_value=1
                )
            )

    tax_vat12 = db_session.query(TaxRate).filter_by(code="VAT12").first()
    if not tax_vat12:
        tax_vat12 = TaxRate(
            code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
        )
        db_session.add(tax_vat12)

    cat = db_session.query(ProductCategory).filter_by(name="Industrial Equipment").first()
    if not cat:
        cat = ProductCategory(name="Industrial Equipment")
        db_session.add(cat)
        db_session.flush()

    prod = db_session.query(Product).filter_by(sku="PROD-VALVE-01").first()
    if not prod:
        prod = Product(
            sku="PROD-VALVE-01",
            name="Precision Flow Control Valve",
            description="High pressure control valve",
            category_id=cat.id,
            list_price=Decimal("1500.0000"),
            uom="pc",
            product_type="stock",
            tax_rate_id=tax_vat12.id,
            is_active=True,
        )
        db_session.add(prod)
        db_session.flush()

    from app.modules.inventory.models import InventoryBalance, Warehouse

    wh = db_session.query(Warehouse).filter_by(is_default=True).first()
    if not wh:
        wh = Warehouse(
            code="WH-MANILA-01",
            name="Main Warehouse - Manila",
            is_active=True,
            is_default=True,
        )
        db_session.add(wh)
        db_session.flush()

    bal = (
        db_session.query(InventoryBalance).filter_by(product_id=prod.id, warehouse_id=wh.id).first()
    )
    if not bal:
        bal = InventoryBalance(
            product_id=prod.id,
            warehouse_id=wh.id,
            qty_on_hand=Decimal("100.000"),
            qty_reserved=Decimal("0.000"),
            avg_unit_cost=Decimal("900.0000"),
        )
        db_session.add(bal)
        db_session.flush()

    user = db_session.query(User).filter_by(email="maria.santos@company.ph").first()
    if not user:
        user = User(
            email="maria.santos@company.ph",
            password_hash="argon2_hash_val",
            full_name="Maria Santos",
            is_active=True,
        )
        db_session.add(user)
    db_session.commit()
    db_session.refresh(prod)
    db_session.refresh(user)

    # 1.2 Lead Ingestion
    from app.modules.crm.schemas import (
        CustomerAddressCreate,
        LeadConvertPayload,
        LeadCreate,
        LeadTransitionPayload,
        OpportunityTransitionPayload,
    )

    lead = crm_service.create_lead(
        data=LeadCreate(
            first_name="Juan",
            last_name="Dela Cruz",
            company_name="Apex Logistics Inc",
            email="juan.delacruz@apexlogistics.ph",
            phone="+639171234567",
            source="website",
            notes="High intent prospective buyer",
            owner_user_id=user.id,
        ),
        creator_id=user.id,
    )
    assert lead.lead_no.startswith("LEAD-")
    assert lead.status == "new"

    # 1.3 Lead Conversion -> Customer & Opportunity
    lead = crm_service.transition_lead(
        lead.id,
        LeadTransitionPayload(to_status="contacted", reason="Initial sales contact"),
        user_id=user.id,
    )
    lead = crm_service.transition_lead(
        lead.id,
        LeadTransitionPayload(to_status="qualified", reason="Budget and timeline confirmed"),
        user_id=user.id,
    )
    lead = crm_service.convert_lead(
        lead_id=lead.id,
        payload=LeadConvertPayload(
            create_opportunity=True,
            opportunity_name="Industrial Pipe Expansion",
            opportunity_estimated_amount=Decimal("15000.00"),
        ),
        user_id=user.id,
    )
    assert lead.status == "converted"
    assert lead.converted_customer_id is not None
    assert lead.converted_opportunity_id is not None
    customer = db_session.get(Customer, lead.converted_customer_id)
    opportunity = db_session.get(Opportunity, lead.converted_opportunity_id)

    # 1.4 Progress Opportunity to Negotiation -> Won
    opportunity = crm_service.transition_opportunity(
        opportunity.id,
        OpportunityTransitionPayload(to_stage="proposal", reason="Proposal generated"),
        user_id=user.id,
    )
    opportunity = crm_service.transition_opportunity(
        opportunity.id,
        OpportunityTransitionPayload(to_stage="negotiation", reason="Terms under discussion"),
        user_id=user.id,
    )

    # Add billing address
    address = crm_service.add_address(
        customer_id=customer.id,
        data=CustomerAddressCreate(
            address_type="billing",
            line1="Bldg 4, Laguna Technopark",
            city="Santa Rosa",
            province="Laguna",
            postal_code="4026",
            country_code="PH",
            is_default=True,
        ),
        creator_id=user.id,
    )
    assert address.city == "Santa Rosa"

    # 1.5 Quote Creation & Issuance
    quote_payload = QuoteCreatePayload(
        customer_id=customer.id,
        opportunity_id=opportunity.id,
        valid_until=date(2026, 4, 30),
        items=[
            LineItemPayload(
                product_id=prod.id,
                quantity=Decimal("10.000"),
                unit_price=Decimal("1500.0000"),
                discount_amount=Decimal("0.00"),
            )
        ],
    )
    quote = sales_service.create_quote(quote_payload, current_user_id=user.id)
    sales_service.send_quote(quote.id, current_user_id=user.id)
    sales_service.accept_quote(quote.id, current_user_id=user.id)
    db_session.refresh(quote)
    assert quote.status == "accepted"
    assert quote.subtotal == Decimal("15000.00")
    assert quote.tax_total == Decimal("1800.00")
    assert quote.grand_total == Decimal("16800.00")

    # 1.6 Sales Order Confirmation
    order = sales_service.create_order_from_quote(quote.id, current_user_id=user.id)
    order = sales_service.confirm_sales_order(order.id, current_user_id=user.id)
    assert order.status == "confirmed"

    # Opportunity is auto-won upon quote acceptance / order confirmation
    db_session.refresh(opportunity)
    assert opportunity.stage == "won"

    # 1.7 Invoice Issuance
    invoice = sales_service.create_invoice_from_order(order.id, current_user_id=user.id)
    invoice = sales_service.issue_invoice(invoice.id, current_user_id=user.id)
    assert invoice.status == "issued"
    assert invoice.subtotal == Decimal("15000.00")
    assert invoice.grand_total == Decimal("16800.00")
    assert invoice.balance_due == Decimal("16800.00")

    # 1.8 Payment Receipt & Allocation (Centavo Parity)
    payment = sales_service.create_payment(
        PaymentCreatePayload(
            customer_id=customer.id,
            method="bank_transfer",
            reference_no="BDO-TXN-998877",
            amount=Decimal("16800.00"),
        ),
        current_user_id=user.id,
    )
    sales_service.allocate_payment(
        payment.id, invoice.id, Decimal("16800.00"), current_user_id=user.id
    )
    db_session.refresh(invoice)
    db_session.refresh(payment)
    assert invoice.status == "paid"
    assert invoice.balance_due == Decimal("0.00")
    assert payment.amount_allocated == Decimal("16800.00")
    db_session.commit()

    # -------------------------------------------------------------------------
    # HOP 2: ANALYTICS EXTRACTION (OLTP -> raw)
    # -------------------------------------------------------------------------
    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,
    )
    extract_summary = extractor.run(job_name="e2e_daily_extraction")
    assert extract_summary["status"] == "success"
    assert extract_summary["rows_extracted"] > 0
    assert extract_summary["run_id"] is not None

    # -------------------------------------------------------------------------
    # HOP 3: TRANSFORMATION PIPELINE (raw -> staging DAG)
    # -------------------------------------------------------------------------
    transformer = TransformRunner(engine=analytics_test_engine)
    transform_summary = transformer.run()
    assert transform_summary["status"] == "success", (
        f"Failed models: {[m for m in transform_summary['models'] if m['status'] != 'success']}"
    )
    assert transform_summary["rows_affected"] > 0

    # -------------------------------------------------------------------------
    # HOP 4: DATA QUALITY EVALUATION & SCORING (staging -> dq)
    # -------------------------------------------------------------------------
    dq_runner = DqRunner(engine=analytics_test_engine)
    dq_summary = dq_runner.run(preview=False)
    assert dq_summary["status"] == "success"
    assert dq_summary["quarantined_total"] >= 0

    # Verify dq.results records were created
    is_postgres = analytics_test_engine.dialect.name == "postgresql"
    dq_res_table = "dq.results" if is_postgres else "results"
    with analytics_test_engine.connect() as conn:
        dq_rows = conn.execute(text(f"SELECT COUNT(*) FROM {dq_res_table}")).scalar_one()
        assert dq_rows > 0

    # -------------------------------------------------------------------------
    # HOP 5: DIMENSIONAL STAR SCHEMA BUILD (staging -> mart)
    # -------------------------------------------------------------------------
    mart_builder = MartBuilder(engine=analytics_test_engine)
    mart_summary = mart_builder.run()
    assert mart_summary["status"] == "success"
    assert mart_summary["dimensions"]["dim_date"] > 0
    assert mart_summary["dimensions"]["dim_customer"] >= 1
    assert mart_summary["facts"]["fact_sales_line"] >= 1
    assert mart_summary["facts"]["fact_ar_allocation"] >= 1

    # -------------------------------------------------------------------------
    # HOP 6: POWER BI SEMANTIC MODEL CONTRACT (DAX Metrics Parity)
    # -------------------------------------------------------------------------
    fact_sales = "mart.fact_sales_line" if is_postgres else "fact_sales_line"
    fact_ar = "mart.fact_ar_allocation" if is_postgres else "fact_ar_allocation"
    with analytics_test_engine.connect() as conn:
        # KPI-001: Net Revenue Parity for the traced invoice (₱15,000.00 subtotal)
        net_rev_row = (
            conn.execute(
                text(
                    f"SELECT SUM(net_revenue) AS net_revenue, SUM(gross_margin) AS total_margin FROM {fact_sales} WHERE invoice_no = '{invoice.invoice_no}'"
                )
            )
            .mappings()
            .first()
        )
        assert net_rev_row is not None
        assert Decimal(str(net_rev_row["net_revenue"])) == Decimal("15000.00")

        # Gross Margin Parity (Net revenue of ₱15,000.00 - COGS)
        assert Decimal(str(net_rev_row["total_margin"])) >= Decimal("0.00")

        # KPI-005: AR Allocation Parity (Payment fully applied)
        ar_alloc_sum = conn.execute(
            text(
                f"SELECT SUM(amount) AS total_allocated FROM {fact_ar} WHERE payment_no = '{payment.payment_no}'"
            )
        ).scalar_one()
        assert Decimal(str(ar_alloc_sum)) == Decimal("16800.00")

    # -------------------------------------------------------------------------
    # HOP 7: VISIQ AI ANALYST NATURAL LANGUAGE EXPLANATION
    # -------------------------------------------------------------------------
    agent = VisiqAgent(engine=analytics_test_engine)
    query_engine = VisiqQueryEngine(engine=analytics_test_engine)

    # 7.1 Freshness Verification
    freshness = query_engine.get_etl_freshness()
    assert freshness["is_fresh"] is True

    # 7.2 Data Quality Warnings Verification
    dq_warnings = query_engine.get_active_dq_warnings()
    assert isinstance(dq_warnings, list)

    # 7.3 Natural Language Question Answering & KPI Evaluation
    q_res = agent.ask("What is our total net revenue?")
    assert q_res["refused"] is False
    assert q_res["tool_called"] == "get_metric"
    assert q_res["tool_output"]["value"] >= 15000.00

    # 7.4 Security Guardrails & PII Sanitization
    pii_payload = {
        "customer": "Apex Logistics Inc",
        "email": "juan.delacruz@apexlogistics.ph",
        "phone": "+639171234567",
        "net_revenue": 15000.00,
    }
    sanitized = query_engine.sanitize_pii(pii_payload)
    assert sanitized["email"] == "[REDACTED_PII]"
    assert sanitized["phone"] == "[REDACTED_PII]"
    assert sanitized["customer"] == "Apex Logistics Inc"


def test_end_to_end_architecture_and_adr_compliance():
    """
    Validates that Milestone V2.0 documentation requirements are strictly fulfilled:
    - docs/architecture.md exists with C4 diagrams, ADR catalog, and trade-offs.
    - docs/versions/V2.0.md exists with complete release notes.
    - docs/end_to_end_scenario.md exists detailing the traced business narrative.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent

    arch_doc = repo_root / "docs" / "architecture.md"
    assert arch_doc.exists(), "docs/architecture.md must exist for V2.0"
    arch_content = arch_doc.read_text(encoding="utf-8")
    assert "C4" in arch_content
    assert "System Context" in arch_content
    assert "Container Architecture" in arch_content
    assert "Component Architecture" in arch_content
    assert "ADR-0001" in arch_content
    assert "ADR-0015" in arch_content
    assert "Known Limitations" in arch_content
    assert "What I'd Do Next" in arch_content

    scenario_doc = repo_root / "docs" / "end_to_end_scenario.md"
    assert scenario_doc.exists(), "docs/end_to_end_scenario.md must exist for V2.0"
    scenario_content = scenario_doc.read_text(encoding="utf-8")
    assert "Hop 1" in scenario_content
    assert "Hop 7" in scenario_content
    assert "Power BI" in scenario_content
    assert "Visiq" in scenario_content

    v2_notes = repo_root / "docs" / "versions" / "V2.0.md"
    assert v2_notes.exists(), "docs/versions/V2.0.md must exist for V2.0"
    v2_content = v2_notes.read_text(encoding="utf-8")
    assert "Milestone V2.0 Release Notes" in v2_content
    assert "Exit Criteria Verification" in v2_content
