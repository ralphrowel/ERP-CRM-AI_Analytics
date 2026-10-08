"""V0.2 schema: CRM Core (leads, contacts, opportunities, activities, status_history)

Revision ID: 0002_crm_core
Revises: 0001_initial_schema
Create Date: 2026-10-08 13:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_crm_core"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. status_history table (Roadmap §4.6)
    op.create_table(
        "status_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.BigInteger(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_status_history_lookup", "status_history", ["entity_type", "entity_id", "changed_at"]
    )

    # 2. contacts table
    op.create_table(
        "contacts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("job_title", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contacts_customer_id", "contacts", ["customer_id"])
    op.create_index(
        "uq_customer_primary_contact",
        "contacts",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_primary AND is_active"),
    )
    op.execute("""
    CREATE TRIGGER trg_contacts_updated_at
    BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 3. leads table
    op.create_table(
        "leads",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("lead_no", sa.String(length=30), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=30), server_default="website", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="new", nullable=False),
        sa.Column("disqualified_reason", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_customer_id", sa.BigInteger(), nullable=True),
        sa.Column("converted_contact_id", sa.BigInteger(), nullable=True),
        sa.Column("converted_opportunity_id", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "source IN ('website', 'referral', 'event', 'cold_call', 'social', 'import', 'other')",
            name="ck_leads_source",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'disqualified', 'converted')",
            name="ck_leads_status",
        ),
        sa.CheckConstraint(
            "status <> 'converted' OR (converted_at IS NOT NULL AND converted_customer_id IS NOT NULL)",
            name="ck_leads_converted_consistency",
        ),
        sa.CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL", name="ck_leads_has_contact_info"
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_no"),
    )
    op.create_index("ix_leads_owner_user_id", "leads", ["owner_user_id"])
    op.execute("""
    CREATE TRIGGER trg_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 4. opportunities table
    op.create_table(
        "opportunities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("opportunity_no", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("primary_contact_id", sa.BigInteger(), nullable=True),
        sa.Column("stage", sa.String(length=30), server_default="discovery", nullable=False),
        sa.Column(
            "estimated_amount",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "probability", sa.Numeric(precision=6, scale=4), server_default="0.2000", nullable=False
        ),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.String(length=50), nullable=True),
        sa.Column("source_lead_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "stage IN ('discovery', 'proposal', 'negotiation', 'won', 'lost')",
            name="ck_opportunities_stage",
        ),
        sa.CheckConstraint(
            "estimated_amount >= 0", name="ck_opportunities_estimated_amount_positive"
        ),
        sa.CheckConstraint(
            "probability BETWEEN 0 AND 1", name="ck_opportunities_probability_range"
        ),
        sa.CheckConstraint(
            "(stage IN ('won', 'lost')) = (closed_at IS NOT NULL)",
            name="ck_opportunities_closed_at_consistent",
        ),
        sa.CheckConstraint(
            "stage <> 'lost' OR lost_reason IS NOT NULL",
            name="ck_opportunities_lost_reason_required",
        ),
        sa.CheckConstraint(
            "lost_reason IS NULL OR lost_reason IN ('price', 'competitor', 'no_budget', 'no_decision', 'timing', 'other')",
            name="ck_opportunities_lost_reason_valid",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_no"),
    )
    op.create_index("ix_opportunities_customer_id", "opportunities", ["customer_id"])
    op.create_index("ix_opportunities_owner_user_id", "opportunities", ["owner_user_id"])
    op.execute("""
    CREATE TRIGGER trg_opportunities_updated_at
    BEFORE UPDATE ON opportunities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Connect FK on leads.converted_opportunity_id now that opportunities table exists
    op.create_foreign_key(
        "fk_leads_converted_opportunity",
        "leads",
        "opportunities",
        ["converted_opportunity_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 5. activities table
    op.create_table(
        "activities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("activity_type", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("lead_id", sa.BigInteger(), nullable=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=True),
        sa.Column("contact_id", sa.BigInteger(), nullable=True),
        sa.Column("opportunity_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "activity_type IN ('call', 'email', 'meeting', 'task', 'note')",
            name="ck_activities_type",
        ),
        sa.CheckConstraint(
            "num_nonnulls(lead_id, customer_id, contact_id, opportunity_id) >= 1",
            name="ck_activities_at_least_one_relation",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activities_lead_id", "activities", ["lead_id"])
    op.create_index("ix_activities_customer_id", "activities", ["customer_id"])
    op.create_index("ix_activities_opportunity_id", "activities", ["opportunity_id"])
    op.execute("""
    CREATE TRIGGER trg_activities_updated_at
    BEFORE UPDATE ON activities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 6. Seed document sequences for lead and opportunity (Roadmap §4.5)
    op.execute("""
    INSERT INTO document_sequences (doc_type, prefix, include_year, padding, current_year, next_value)
    VALUES
        ('lead', 'LEAD', false, 6, NULL, 1),
        ('opportunity', 'OPP', false, 6, NULL, 1)
    ON CONFLICT (doc_type) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_activities_updated_at ON activities;")
    op.execute("DROP TRIGGER IF EXISTS trg_opportunities_updated_at ON opportunities;")
    op.execute("DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads;")
    op.execute("DROP TRIGGER IF EXISTS trg_contacts_updated_at ON contacts;")

    op.drop_table("activities")
    op.drop_constraint("fk_leads_converted_opportunity", "leads", type_="foreignkey")
    op.drop_table("opportunities")
    op.drop_table("leads")
    op.drop_table("contacts")
    op.drop_table("status_history")

    op.execute("DELETE FROM document_sequences WHERE doc_type IN ('lead', 'opportunity');")
