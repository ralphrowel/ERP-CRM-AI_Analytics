"""
Entity Resolution Engine (Roadmap §V1.3)
Links historical legacy customer identifiers (legacy_customer_id) to
operational ERP customers (customers.id) via a 3-tier deterministic & fuzzy matching cascade:
1. Exact TIN / Tax ID match (Confidence: 1.00)
2. Exact Email match (Confidence: 0.95)
3. Normalized Corporate Name similarity >= 0.85 (Confidence: similarity score)
Persisted in dq.entity_map table.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import Engine, text


@dataclass
class EntityMatch:
    legacy_customer_id: str
    erp_customer_id: int
    match_method: str  # tax_id_exact, email_exact, name_fuzzy
    confidence: float
    legacy_name: str
    erp_name: str


CORPORATE_SUFFIXES = [
    r"\binc\b\.?",
    r"\bincorporated\b",
    r"\bcorp\b\.?",
    r"\bcorporation\b",
    r"\bco\b\.?",
    r"\bcompany\b",
    r"\bltd\b\.?",
    r"\blimited\b",
    r"\bholdings\b",
    r"\bsystems\b",
    r"\bgroup\b",
    r"\bph\b\.?",
    r"\bdev\b\.?",
    r"\bdevelopment\b",
    r"\bengineering\b",
    r"\beng\b\.?",
    r"\bpackaging\b",
    r"\blogistics\b",
    r"\bhub\b",
    r"\bclub\b",
    r"\bprice\b",
]


def normalize_tin(tin: str | None) -> str:
    """Strips hyphens and whitespace from Philippine Tax Identification Number."""
    if not tin:
        return ""
    return re.sub(r"[^\d]", "", tin.strip())


def normalize_email(email: str | None) -> str:
    """Normalizes contact email for exact identity matching."""
    if not email:
        return ""
    clean = email.strip().lower()
    if clean in ("n/a", "na", "null", "none@domain"):
        return ""
    return clean


def normalize_company_name(name: str | None) -> str:
    """Normalizes company names by lowercasing, removing punctuation, and stripping corporate suffixes."""
    if not name:
        return ""
    s = name.lower().strip()
    # Remove punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    # Strip corporate suffixes
    for suffix in CORPORATE_SUFFIXES:
        s = re.sub(suffix, " ", s, flags=re.IGNORECASE)
    # Collapse multiple whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compute_name_similarity(name1: str, name2: str) -> float:
    """Computes normalized string similarity ratio between two company names."""
    norm1 = normalize_company_name(name1)
    norm2 = normalize_company_name(name2)
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.00
    # Quick containment check for common abbreviations
    if (len(norm1) > 4 and norm1 in norm2) or (len(norm2) > 4 and norm2 in norm1):
        shorter = min(len(norm1), len(norm2))
        longer = max(len(norm1), len(norm2))
        return round(shorter / longer, 4)
    return round(SequenceMatcher(None, norm1, norm2).ratio(), 4)


def resolve_entities(
    legacy_customers: list[dict[str, Any]],
    erp_customers: list[dict[str, Any]],
    similarity_threshold: float = 0.85,
) -> list[EntityMatch]:
    """
    Executes entity resolution matching cascade between legacy customers and ERP customers.
    Returns list of EntityMatch results.
    """
    matches: list[EntityMatch] = []
    matched_legacy_ids: set[str] = set()

    # Pre-index ERP customers by normalized TIN and normalized Email
    erp_by_tin: dict[str, dict[str, Any]] = {}
    erp_by_email: dict[str, dict[str, Any]] = {}

    for erp in erp_customers:
        tin = normalize_tin(erp.get("tin"))
        if tin:
            erp_by_tin[tin] = erp

        email = normalize_email(erp.get("email"))
        if email:
            erp_by_email[email] = erp

    # Pass 1: Exact TIN Match (Confidence 1.00)
    for leg in legacy_customers:
        leg_id = str(leg.get("legacy_customer_id") or "")
        if not leg_id:
            continue

        tax_id = normalize_tin(leg.get("tax_id") or leg.get("parsed_tax_id"))
        if tax_id and tax_id in erp_by_tin:
            erp = erp_by_tin[tax_id]
            matches.append(
                EntityMatch(
                    legacy_customer_id=leg_id,
                    erp_customer_id=int(erp["id"]),
                    match_method="tax_id_exact",
                    confidence=1.00,
                    legacy_name=str(leg.get("customer_name") or ""),
                    erp_name=str(erp.get("name") or ""),
                )
            )
            matched_legacy_ids.add(leg_id)

    # Pass 2: Exact Email Match (Confidence 0.95)
    for leg in legacy_customers:
        leg_id = str(leg.get("legacy_customer_id") or "")
        if not leg_id or leg_id in matched_legacy_ids:
            continue

        email = normalize_email(leg.get("contact_email"))
        if email and email in erp_by_email:
            erp = erp_by_email[email]
            matches.append(
                EntityMatch(
                    legacy_customer_id=leg_id,
                    erp_customer_id=int(erp["id"]),
                    match_method="email_exact",
                    confidence=0.95,
                    legacy_name=str(leg.get("customer_name") or ""),
                    erp_name=str(erp.get("name") or ""),
                )
            )
            matched_legacy_ids.add(leg_id)

    # Pass 3: Fuzzy Company Name Similarity (Confidence >= similarity_threshold)
    for leg in legacy_customers:
        leg_id = str(leg.get("legacy_customer_id") or "")
        if not leg_id or leg_id in matched_legacy_ids:
            continue

        leg_name = str(leg.get("customer_name") or "")
        best_match: dict[str, Any] | None = None
        best_score = 0.0

        for erp in erp_customers:
            erp_name = str(erp.get("name") or "")
            sim = compute_name_similarity(leg_name, erp_name)
            if sim > best_score:
                best_score = sim
                best_match = erp

        if best_match and best_score >= similarity_threshold:
            matches.append(
                EntityMatch(
                    legacy_customer_id=leg_id,
                    erp_customer_id=int(best_match["id"]),
                    match_method="name_fuzzy",
                    confidence=best_score,
                    legacy_name=leg_name,
                    erp_name=str(best_match.get("name") or ""),
                )
            )
            matched_legacy_ids.add(leg_id)

    return matches


def persist_entity_matches(
    matches: list[EntityMatch],
    engine: Engine,
    run_id: int,
    clock_now: datetime | None = None,
) -> int:
    """Persists resolved entity matches into dq.entity_map table."""
    now = clock_now or datetime.now(UTC)
    is_postgres = engine.dialect.name == "postgresql"
    target_table = "dq.entity_map" if is_postgres else "entity_map"

    if not matches:
        return 0

    with engine.begin() as conn:
        for m in matches:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {target_table} (
                        run_id, legacy_customer_id, erp_customer_id, match_method, confidence, created_at
                    ) VALUES (
                        :run_id, :legacy_id, :erp_id, :method, :confidence, :created_at
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "legacy_id": m.legacy_customer_id,
                    "erp_id": m.erp_customer_id,
                    "method": m.match_method,
                    "confidence": m.confidence,
                    "created_at": now,
                },
            )
    return len(matches)
