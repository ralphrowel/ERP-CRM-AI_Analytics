"""
Data Quality Module (Roadmap §V1.3)
Visiq Data Quality Engine integrating 4D quality scoring, non-destructive cleaning,
entity resolution, quarantine, and circuit breaking.
"""

from analytics.dq.cleaner import preview_cleaning, to_safe_csv_text
from analytics.dq.models import DqEntityMap, DqIssue, DqLineage, DqQuarantine, DqResult
from analytics.dq.profiler import profile_dataset
from analytics.dq.resolution import resolve_entities
from analytics.dq.runner import CircuitBreakerError, DqRunner
from analytics.dq.scoring import calculate_quality_scorecard, score_to_letter_grade

__all__ = [
    "CircuitBreakerError",
    "DqEntityMap",
    "DqIssue",
    "DqLineage",
    "DqQuarantine",
    "DqResult",
    "DqRunner",
    "calculate_quality_scorecard",
    "preview_cleaning",
    "profile_dataset",
    "resolve_entities",
    "score_to_letter_grade",
    "to_safe_csv_text",
]
