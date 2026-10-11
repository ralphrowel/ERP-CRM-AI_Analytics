"""
Visiq 4-Dimension Quality Scoring Model (Roadmap §V1.3)
Computes dimension sub-scores (Completeness 30%, Validity 30%, Uniqueness 20%, Consistency 20%),
calculates composite health score (0–100), and assigns letter grades (A–F).
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

DIMENSION_WEIGHTS: dict[str, float] = {
    "Completeness": 0.30,
    "Validity": 0.30,
    "Uniqueness": 0.20,
    "Consistency": 0.20,
}


def score_to_letter_grade(score: float) -> str:
    """Assigns enterprise letter grade based on composite score."""
    if score >= 90.0:
        return "A"
    if score >= 80.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 60.0:
        return "D"
    return "F"


@dataclass
class RuleEvaluationResult:
    rule_name: str
    dimension: str
    column: str
    total_rows: int
    failed_rows: int
    severity: str = "WARNING"  # CRITICAL, WARNING, INFO

    @property
    def pass_rate(self) -> float:
        if self.total_rows == 0:
            return 100.0
        passed = max(0, self.total_rows - self.failed_rows)
        return round((passed / self.total_rows) * 100.0, 2)


@dataclass
class QualityScorecard:
    dataset: str
    composite_score: float
    letter_grade: str
    dimension_scores: dict[str, float]
    rule_results: list[RuleEvaluationResult] = field(default_factory=list)
    total_issues: int = 0
    critical_failures: int = 0


def calculate_quality_scorecard(
    dataset: str,
    rule_results: list[RuleEvaluationResult],
) -> QualityScorecard:
    """
    Computes dimension scores and weighted composite quality score.
    Completeness: 30%
    Validity: 30%
    Uniqueness: 20%
    Consistency: 20%
    """
    dimension_results: dict[str, list[RuleEvaluationResult]] = {
        "Completeness": [],
        "Validity": [],
        "Uniqueness": [],
        "Consistency": [],
    }

    critical_count = 0
    total_issue_count = 0

    for r in rule_results:
        total_issue_count += r.failed_rows
        if r.severity == "CRITICAL" and r.failed_rows > 0:
            critical_count += 1
        dim = r.dimension if r.dimension in dimension_results else "Validity"
        dimension_results[dim].append(r)

    dimension_scores: dict[str, float] = {}
    composite_sum = 0.0

    for dim, weight in DIMENSION_WEIGHTS.items():
        rules = dimension_results[dim]
        if not rules:
            dim_score = 100.0
        else:
            dim_score = sum(r.pass_rate for r in rules) / len(rules)
        dim_score = round(max(0.0, min(100.0, dim_score)), 2)
        dimension_scores[dim] = dim_score
        composite_sum += dim_score * weight

    # Quantize to 2 decimals
    final_score = float(
        Decimal(str(composite_sum)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    final_score = max(0.0, min(100.0, final_score))
    grade = score_to_letter_grade(final_score)

    return QualityScorecard(
        dataset=dataset,
        composite_score=final_score,
        letter_grade=grade,
        dimension_scores=dimension_scores,
        rule_results=rule_results,
        total_issues=total_issue_count,
        critical_failures=critical_count,
    )
