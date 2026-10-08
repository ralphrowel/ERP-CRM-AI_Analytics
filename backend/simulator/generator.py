import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import ControllableClock
from app.modules.crm.schemas import (
    ActivityCreate,
    LeadConvertPayload,
    LeadCreate,
    LeadTransitionPayload,
    OpportunityTransitionPayload,
)
from app.modules.crm.service import CRMService
from app.modules.identity.models import User
from app.modules.identity.schemas import UserCreate
from app.modules.identity.service import IdentityService
from app.modules.organization.models import Department
from app.modules.organization.schemas import DepartmentCreate, EmployeeCreate
from app.modules.organization.service import OrganizationService

FIRST_NAMES = [
    "Mateo",
    "Maria",
    "Gabriel",
    "Sofia",
    "Alejandro",
    "Isabella",
    "Rafael",
    "Camila",
    "Marco",
    "Beatriz",
    "Diego",
    "Patricia",
    "Antonio",
    "Elena",
    "Fernando",
    "Clara",
]
LAST_NAMES = [
    "Santos",
    "Reyes",
    "Cruz",
    "Bautista",
    "Ocampo",
    "Garcia",
    "Mendoza",
    "Torres",
    "Castillo",
    "Flores",
    "Villanueva",
    "Ramos",
    "Aquino",
    "Navarro",
    "Mercado",
    "Del Rosario",
]
COMPANY_NAMES = [
    "Ayala Logistics Corp.",
    "San Miguel Packaging",
    "JG Summit Holdings",
    "Megawide Engineering",
    "Aboitiz Power Systems",
    "DMCI Holdings PH",
    "Robinsons Retail Hub",
    "Monde Nissin Distribution",
    "Universal Robina Lines",
    "Alliance Global Group",
    "Filinvest Land Dev",
    "Century Pacific Foods",
    "ICTSI Manila Terminal",
    "PLDT Infrastructure",
    "Globe Telecom Systems",
    "Security Bank Commercial",
]
JOB_TITLES = [
    "Procurement Manager",
    "Operations Director",
    "Purchasing Officer",
    "Supply Chain Lead",
    "Managing Director",
    "VP of Operations",
    "IT Systems Architect",
    "General Manager",
]
LOST_REASONS = ["price", "competitor", "no_budget", "no_decision", "timing", "other"]


class Simulator:
    def __init__(self, db: Session, seed: int = 42, months: int = 6) -> None:
        self.db = db
        self.seed = seed
        self.months = months
        random.seed(seed)

        # Start simulation 6 months ago (Manila business hours)
        self.start_time = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        self.clock = ControllableClock(self.start_time)

        self.identity_svc = IdentityService(db, clock=self.clock)
        self.org_svc = OrganizationService(db, clock=self.clock)
        self.crm_svc = CRMService(db, clock=self.clock)

    def run(self) -> dict[str, int]:
        """Runs deterministic simulation using domain services and controllable clock."""
        # 1. Setup Base Organization & Sales Team
        self.identity_svc.bootstrap_superuser()
        self.org_svc.get_or_create_settings()

        sales_dept = self.db.query(Department).filter_by(code="SALES").first()
        if not sales_dept:
            sales_dept = self.org_svc.create_department(
                DepartmentCreate(code="SALES", name="Commercial Sales")
            )

        # Create 3 Sales Reps
        sales_users: list[User] = []
        for fn, ln in [("Carlos", "Reyes"), ("Maria", "Santos"), ("Paolo", "Cruz")]:
            email = f"{fn.lower()}.{ln.lower()}@enterprise.local"
            user = self.db.query(User).filter_by(email=email).first()
            if not user:
                user = self.identity_svc.create_user(
                    UserCreate(
                        email=email,
                        password="Password123456!",
                        full_name=f"{fn} {ln}",
                        is_superuser=False,
                    )
                )
                self.org_svc.create_employee(
                    EmployeeCreate(
                        first_name=fn,
                        last_name=ln,
                        email=email,
                        department_id=sales_dept.id,
                        job_title="Senior Account Executive",
                        user_id=user.id,
                        hire_date=self.clock.today(),
                    ),
                    creator_id=user.id,
                )
            sales_users.append(user)

        total_days = self.months * 30
        leads_created = 0
        leads_converted = 0
        opps_won = 0
        opps_lost = 0
        activities_count = 0

        # Day-by-day progression
        for _day in range(total_days):
            self.clock.advance(days=1)
            # Skip Sundays
            if self.clock.now().weekday() == 6:
                continue

            # Daily: 1 to 3 new leads captured
            daily_lead_count = random.randint(1, 3)
            for _ in range(daily_lead_count):
                fn = random.choice(FIRST_NAMES)
                ln = random.choice(LAST_NAMES)
                company = random.choice(COMPANY_NAMES)
                rep = random.choice(sales_users)
                source = random.choices(
                    ["website", "referral", "event", "cold_call", "social"],
                    weights=[0.35, 0.25, 0.15, 0.15, 0.10],
                )[0]

                lead = self.crm_svc.create_lead(
                    LeadCreate(
                        first_name=fn,
                        last_name=ln,
                        company_name=company,
                        job_title=random.choice(JOB_TITLES),
                        email=f"{fn.lower()}.{ln.lower()}@{company.split()[0].lower()}.ph",
                        phone=f"+63 917 {random.randint(100, 999)} {random.randint(1000, 9999)}",
                        source=source,
                        owner_user_id=rep.id,
                    ),
                    creator_id=rep.id,
                )
                leads_created += 1

                # Log initial activity
                self.crm_svc.create_activity(
                    ActivityCreate(
                        activity_type="note",
                        subject=f"Inbound lead received from {source}",
                        lead_id=lead.id,
                        owner_user_id=rep.id,
                    ),
                    creator_id=rep.id,
                )
                activities_count += 1

                # Funnel simulation:
                # 60% transition to 'contacted'
                if random.random() < 0.60:
                    self.crm_svc.transition_lead(
                        lead.id,
                        LeadTransitionPayload(
                            to_status="contacted", reason="Initial discovery call completed"
                        ),
                        user_id=rep.id,
                    )
                    self.crm_svc.create_activity(
                        ActivityCreate(
                            activity_type="call",
                            subject="Initial discovery call",
                            lead_id=lead.id,
                            owner_user_id=rep.id,
                        ),
                        creator_id=rep.id,
                    )
                    activities_count += 1

                    # 35% of contacted transition to 'qualified' (or disqualified)
                    if random.random() < 0.58:  # 0.60 * 0.58 ~ 35%
                        self.crm_svc.transition_lead(
                            lead.id,
                            LeadTransitionPayload(
                                to_status="qualified",
                                reason="Budget and purchase authority verified",
                            ),
                            user_id=rep.id,
                        )

                        # 70% of qualified get converted (~25% overall conversion rate)
                        if random.random() < 0.70:
                            deal_size = Decimal(
                                str(random.choice([150000, 250000, 500000, 750000, 1200000]))
                            )
                            converted_lead = self.crm_svc.convert_lead(
                                lead.id,
                                LeadConvertPayload(
                                    create_opportunity=True,
                                    opportunity_name=f"Enterprise Supply - {company}",
                                    opportunity_estimated_amount=deal_size,
                                    expected_close_date=self.clock.today()
                                    + timedelta(days=random.randint(30, 90)),
                                ),
                                user_id=rep.id,
                            )
                            leads_converted += 1

                            # Advance opportunity through stages
                            opp_id = converted_lead.converted_opportunity_id
                            if opp_id:
                                # Proposal stage
                                self.crm_svc.transition_opportunity(
                                    opp_id,
                                    OpportunityTransitionPayload(
                                        to_stage="proposal", reason="Technical proposal submitted"
                                    ),
                                    user_id=rep.id,
                                )
                                self.crm_svc.create_activity(
                                    ActivityCreate(
                                        activity_type="meeting",
                                        subject="Commercial proposal review",
                                        opportunity_id=opp_id,
                                        owner_user_id=rep.id,
                                    ),
                                    creator_id=rep.id,
                                )
                                activities_count += 1

                                # Negotiation stage (70% progress from proposal)
                                if random.random() < 0.70:
                                    self.crm_svc.transition_opportunity(
                                        opp_id,
                                        OpportunityTransitionPayload(
                                            to_stage="negotiation",
                                            reason="Contract pricing finalized",
                                        ),
                                        user_id=rep.id,
                                    )

                                    # Close deal: ~50% won, 50% lost
                                    if random.random() < 0.50:
                                        self.crm_svc.transition_opportunity(
                                            opp_id,
                                            OpportunityTransitionPayload(
                                                to_stage="won",
                                                reason="Contract signed and approved",
                                            ),
                                            user_id=rep.id,
                                        )
                                        opps_won += 1
                                    else:
                                        reason = random.choice(LOST_REASONS)
                                        self.crm_svc.transition_opportunity(
                                            opp_id,
                                            OpportunityTransitionPayload(
                                                to_stage="lost", lost_reason=reason
                                            ),
                                            user_id=rep.id,
                                        )
                                        opps_lost += 1
                                else:
                                    reason = random.choice(LOST_REASONS)
                                    self.crm_svc.transition_opportunity(
                                        opp_id,
                                        OpportunityTransitionPayload(
                                            to_stage="lost", lost_reason=reason
                                        ),
                                        user_id=rep.id,
                                    )
                                    opps_lost += 1
                    else:
                        self.crm_svc.transition_lead(
                            lead.id,
                            LeadTransitionPayload(
                                to_status="disqualified",
                                reason="No purchase budget this calendar year",
                            ),
                            user_id=rep.id,
                        )

        return {
            "leads_created": leads_created,
            "leads_converted": leads_converted,
            "opportunities_won": opps_won,
            "opportunities_lost": opps_lost,
            "activities_recorded": activities_count,
        }
