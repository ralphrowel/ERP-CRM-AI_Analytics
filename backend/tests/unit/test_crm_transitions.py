from decimal import Decimal

from app.modules.crm.service import (
    LEAD_ALLOWED_TRANSITIONS,
    OPP_ALLOWED_TRANSITIONS,
    STAGE_PROBABILITIES,
)


def test_transition_matrix_rules():
    # Verify lead state machine definitions
    assert "contacted" in LEAD_ALLOWED_TRANSITIONS["new"]
    assert "qualified" in LEAD_ALLOWED_TRANSITIONS["new"]
    assert "disqualified" in LEAD_ALLOWED_TRANSITIONS["new"]
    assert "converted" not in LEAD_ALLOWED_TRANSITIONS["new"]
    assert "converted" in LEAD_ALLOWED_TRANSITIONS["qualified"]

    # Converted is terminal
    assert len(LEAD_ALLOWED_TRANSITIONS["converted"]) == 0

    # Opportunity stages
    assert "proposal" in OPP_ALLOWED_TRANSITIONS["discovery"]
    assert "won" not in OPP_ALLOWED_TRANSITIONS["discovery"]
    assert "won" in OPP_ALLOWED_TRANSITIONS["negotiation"]
    assert len(OPP_ALLOWED_TRANSITIONS["won"]) == 0
    assert len(OPP_ALLOWED_TRANSITIONS["lost"]) == 0

    # Standard stage probabilities
    assert STAGE_PROBABILITIES["discovery"] == Decimal("0.2000")
    assert STAGE_PROBABILITIES["proposal"] == Decimal("0.5000")
    assert STAGE_PROBABILITIES["negotiation"] == Decimal("0.7500")
    assert STAGE_PROBABILITIES["won"] == Decimal("1.0000")
    assert STAGE_PROBABILITIES["lost"] == Decimal("0.0000")
