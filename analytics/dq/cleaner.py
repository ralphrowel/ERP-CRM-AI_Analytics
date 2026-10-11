"""
Non-Destructive Data Cleaner & Formula Sanitizer (Roadmap §V1.3 & Visiq Spec §4.5)
Executes non-destructive data cleaning producing staging.clean_* derived tables:
- Never mutates raw tables or operational ERP database in place.
- Neutralizes spreadsheet formula injection via to_safe_csv_text (escaping =, +, -, @, \\t, \\r).
- In-memory dry-run preview (preview_cleaning) projecting cell diffs and scorecard gains.
- Logs transformation audit trail and timings into dq.lineage.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from analytics.dq.rules import (
    CANONICAL_CUSTOMER_ENTITIES,
    CITY_SPELLING_MAP,
    KNOWN_ORPHAN_SKUS,
    QualityRule,
)
from analytics.dq.scoring import calculate_quality_scorecard


@dataclass
class CleaningDiff:
    row_key: str
    column: str
    original_value: Any
    cleaned_value: Any


@dataclass
class CleaningPreview:
    dataset: str
    original_score: float
    original_grade: str
    projected_score: float
    projected_grade: str
    cell_diff_count: int
    coerced_null_count: int
    quarantined_count: int
    sample_diffs: list[CleaningDiff] = field(default_factory=list)


def to_safe_csv_text(val: Any) -> Any:
    """
    Neutralizes spreadsheet formula injection by escaping leading control characters
    (=, +, -, @, \\t, \\r) with single quotes.
    Preserves purely numeric negative values if not string formatted.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val

    s = str(val)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        # If it's a signed numeric string like "-30" or "+5", we only escape if formula-like or explicit text
        if s[0] == "-" and re.match(r"^-\d+(\.\d+)?$", s):
            return s  # preserve standard negative number
        return f"'{s}"
    return s


def clean_customer_row(
    row: dict[str, Any],
    row_key_col: str = "legacy_customer_id",
) -> tuple[dict[str, Any], list[CleaningDiff], int]:
    """Cleans a legacy customer row non-destructively."""
    cleaned = dict(row)
    diffs: list[CleaningDiff] = []
    coerced_nulls = 0
    key = str(row.get(row_key_col) or row.get("_row_number", ""))

    # 1. Contact Email
    em = row.get("contact_email")
    if em is not None:
        s_em = str(em).strip()
        if s_em.upper() in ("N/A", "NA", "NONE", "") or s_em.lower() == "none@domain":
            cleaned["contact_email"] = None
            diffs.append(CleaningDiff(key, "contact_email", em, None))
            coerced_nulls += 1
        else:
            cleaned["contact_email"] = s_em

    # 2. Phone Number -> Standard 11-digit 09XXXXXXXXX
    ph = row.get("phone_number")
    if ph is not None:
        s_ph = str(ph).strip()
        digits = re.sub(r"[^\d]", "", s_ph)
        if digits.startswith("63"):
            digits = "0" + digits[2:]
        if len(digits) == 11 and digits.startswith("09") and digits != s_ph:
            cleaned["phone_number"] = digits
            diffs.append(CleaningDiff(key, "phone_number", ph, digits))

    # 3. City -> Spelling & Whitespace/Casing Standardization
    city = row.get("city")
    if city is not None:
        s_city = str(city)
        canonical = CITY_SPELLING_MAP.get(s_city)
        if not canonical:
            trimmed = s_city.strip()
            if trimmed in CITY_SPELLING_MAP:
                canonical = CITY_SPELLING_MAP[trimmed]
            else:
                canonical = trimmed.title()

        if canonical != s_city:
            cleaned["city"] = canonical
            diffs.append(CleaningDiff(key, "city", city, canonical))

    # 4. Credit Limit -> Clean Numeric
    cl = row.get("credit_limit")
    if cl is not None:
        s_cl = str(cl)
        clean_cl = (
            s_cl.replace("₱", "")
            .replace("PHP", "")
            .replace("php", "")
            .replace(",", "")
            .strip()
        )
        try:
            parsed_cl = float(clean_cl)
            if s_cl != clean_cl and s_cl != str(parsed_cl):
                cleaned["credit_limit"] = clean_cl
                diffs.append(CleaningDiff(key, "credit_limit", cl, clean_cl))
        except ValueError:
            cleaned["credit_limit"] = None
            diffs.append(CleaningDiff(key, "credit_limit", cl, None))
            coerced_nulls += 1

    # 5. Customer Name -> Canonical Entity
    name = row.get("customer_name")
    if name is not None:
        s_name = str(name).strip()
        has_ctrl = bool(s_name and s_name[0] in ("=", "+", "-", "@", "\t", "\r"))
        lookup_name = s_name[1:].strip() if has_ctrl else s_name
        if lookup_name in CANONICAL_CUSTOMER_ENTITIES:
            canonical_name = CANONICAL_CUSTOMER_ENTITIES[lookup_name]
            cleaned["customer_name"] = canonical_name
            diffs.append(CleaningDiff(key, "customer_name", name, canonical_name))
        elif s_name in CANONICAL_CUSTOMER_ENTITIES:
            canonical_name = CANONICAL_CUSTOMER_ENTITIES[s_name]
            cleaned["customer_name"] = canonical_name
            diffs.append(CleaningDiff(key, "customer_name", name, canonical_name))

    # Apply Formula Sanitization to text fields
    for col, val in cleaned.items():
        if isinstance(val, str):
            safe_val = to_safe_csv_text(val)
            if safe_val != val:
                cleaned[col] = safe_val
                diffs.append(CleaningDiff(key, col, val, safe_val))

    return cleaned, diffs, coerced_nulls


def clean_sales_row(
    row: dict[str, Any],
    row_key_col: str = "invoice_no",
) -> tuple[dict[str, Any], list[CleaningDiff], int, bool, str]:
    """
    Cleans a legacy sales row non-destructively.
    Returns: (cleaned_row, diffs, coerced_nulls, is_quarantined, quarantine_reason)
    """
    cleaned = dict(row)
    diffs: list[CleaningDiff] = []
    coerced_nulls = 0
    key = str(row.get(row_key_col) or row.get("_row_number", ""))
    is_quarantined = False
    quarantine_reason = ""

    # 1. Check Critical Negative Quantity
    qty = row.get("quantity")
    if qty is not None:
        try:
            num_qty = float(qty)
            if num_qty < 0:
                is_quarantined = True
                quarantine_reason = f"CRITICAL: Negative quantity {qty}"
        except (ValueError, TypeError):
            is_quarantined = True
            quarantine_reason = f"CRITICAL: Non-numeric quantity {qty}"

    # 2. Check Critical Orphan SKU
    sku = str(row.get("sku") or "").strip()
    if sku in KNOWN_ORPHAN_SKUS or sku.startswith(("UNLISTED-", "OBSOLETE-")):
        is_quarantined = True
        quarantine_reason = f"CRITICAL: Orphan product SKU {sku}"

    # 3. Order Date Normalization
    od = row.get("order_date")
    if od is not None:
        s_od = str(od).strip()
        is_valid = False
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s_od):
            try:
                datetime.strptime(s_od, "%Y-%m-%d").replace(tzinfo=UTC)
                is_valid = True
            except ValueError:
                is_valid = False

        if not is_valid:
            normalized_date: str | None = None
            if re.match(r"^\d{2}/\d{2}/\d{4}$", s_od):
                parts = s_od.split("/")
                normalized_date = f"{parts[2]}-{parts[0]}-{parts[1]}"
            elif re.match(r"^\d{4}\.\d{2}\.\d{2}$", s_od):
                normalized_date = s_od.replace(".", "-")

            if normalized_date:
                try:
                    datetime.strptime(normalized_date, "%Y-%m-%d").replace(tzinfo=UTC)
                    cleaned["order_date"] = normalized_date
                    diffs.append(CleaningDiff(key, "order_date", od, normalized_date))
                except ValueError:
                    is_quarantined = True
                    quarantine_reason = f"CRITICAL: Invalid calendar date {s_od}"
            else:
                is_quarantined = True
                quarantine_reason = f"CRITICAL: Ambiguous/invalid date {s_od}"

    # 4. Total Amount & Unit Price Currency Symbols
    for amt_col in ("total_amount", "unit_price"):
        val = row.get(amt_col)
        if val is not None:
            s_val = str(val)
            clean_amt = (
                s_val.replace("₱", "")
                .replace("PHP", "")
                .replace("php", "")
                .replace(",", "")
                .strip()
            )
            try:
                parsed_amt = float(clean_amt)
                if s_val != clean_amt and s_val != str(parsed_amt):
                    cleaned[amt_col] = clean_amt
                    diffs.append(CleaningDiff(key, amt_col, val, clean_amt))
            except ValueError:
                cleaned[amt_col] = None
                diffs.append(CleaningDiff(key, amt_col, val, None))
                coerced_nulls += 1

    # Apply Formula Sanitization to text fields
    for col, val in cleaned.items():
        if isinstance(val, str):
            safe_val = to_safe_csv_text(val)
            if safe_val != val:
                cleaned[col] = safe_val
                diffs.append(CleaningDiff(key, col, val, safe_val))

    return cleaned, diffs, coerced_nulls, is_quarantined, quarantine_reason


def preview_cleaning(
    dataset: str,
    rows: list[dict[str, Any]],
    rules: list[QualityRule],
    row_key_col: str = "id",
) -> CleaningPreview:
    """
    Executes in-memory dry-run preview of cleaning operations.
    Calculates original score vs projected score improvement without any database writes.
    """
    # 1. Evaluate original scorecard
    orig_rule_results = [r.evaluate(rows, row_key_col)[0] for r in rules]
    orig_scorecard = calculate_quality_scorecard(dataset, orig_rule_results)

    # 2. Clean in-memory
    cleaned_rows: list[dict[str, Any]] = []
    all_diffs: list[CleaningDiff] = []
    total_coerced_nulls = 0
    quarantined_count = 0

    is_sales = "sales" in dataset.lower()

    for r in rows:
        if is_sales:
            cl_row, diffs, coerced, is_quar, _ = clean_sales_row(r, row_key_col)
            if is_quar:
                quarantined_count += 1
            else:
                cleaned_rows.append(cl_row)
        else:
            cl_row, diffs, coerced = clean_customer_row(r, row_key_col)
            cleaned_rows.append(cl_row)

        all_diffs.extend(diffs)
        total_coerced_nulls += coerced

    # 3. Evaluate projected scorecard on clean subset
    eval_rows = cleaned_rows if cleaned_rows else rows
    projected_rule_results = [r.evaluate(eval_rows, row_key_col)[0] for r in rules]
    projected_scorecard = calculate_quality_scorecard(
        f"{dataset}__clean", projected_rule_results
    )

    return CleaningPreview(
        dataset=dataset,
        original_score=orig_scorecard.composite_score,
        original_grade=orig_scorecard.letter_grade,
        projected_score=projected_scorecard.composite_score,
        projected_grade=projected_scorecard.letter_grade,
        cell_diff_count=len(all_diffs),
        coerced_null_count=total_coerced_nulls,
        quarantined_count=quarantined_count,
        sample_diffs=all_diffs[:10],
    )
