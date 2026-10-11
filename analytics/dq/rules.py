"""
Data Quality Rules and Defect Evaluation (Roadmap §V1.3)
Defines enterprise rule evaluators for Visiq's 4 dimensions:
- Completeness (30% weight)
- Validity (30% weight)
- Uniqueness (20% weight)
- Consistency (20% weight)

Detects injected defects (missing email, nonstandard phone, currency symbols,
ambiguous/invalid dates, orphan products, negative quantities, whitespace/casing,
duplicate entities, and spelling variants).
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from analytics.dq.scoring import RuleEvaluationResult


@dataclass
class RuleIssue:
    row_key: str
    column: str
    rule_name: str
    dimension: str
    observed_value: Any
    suggested_value: Any
    severity: str = "WARNING"  # CRITICAL, WARNING, INFO


CANONICAL_CITIES: set[str] = {
    "Makati",
    "Manila",
    "Quezon City",
    "Pasig",
    "Taguig",
    "Mandaluyong",
    "Cebu City",
    "Davao City",
    "Angeles",
    "Baguio",
    "Iloilo City",
    "Calamba",
}

CITY_SPELLING_MAP: dict[str, str] = {
    "MAKATI ": "Makati",
    "Cebu ": "Cebu City",
    " Ortigas, Pasig": "Pasig",
    "BGC, Taguig": "Taguig",
    "Quezon City ": "Quezon City",
    "makati": "Makati",
    "Mnl": "Manila",
    " Manila ": "Manila",
    "Cebu": "Cebu City",
    "City of Manila": "Manila",
    "Pasig City": "Pasig",
    "MANILA": "Manila",
}

CANONICAL_CUSTOMER_ENTITIES: dict[str, str] = {
    "Puregold Price Club Inc.": "Puregold Price Club",
    "San Miguel Packaging, Inc.": "San Miguel Packaging",
    "Ayala Logistics Corporation": "Ayala Logistics Corp.",
    "Aboitiz Power": "Aboitiz Power Systems",
    "D.M.C.I. Holdings": "DMCI Holdings PH",
    "Robinsons Retail": "Robinsons Retail Hub",
    "MEGAWIDE ENG.": "Megawide Engineering",
    "J.G. Summit Holdings Co.": "JG Summit Holdings",
}

KNOWN_ORPHAN_SKUS: set[str] = {"OLD-SYS-999", "UNLISTED-PROD", "OBSOLETE-ITEM"}
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$")
PHONE_STANDARD_REGEX = re.compile(r"^09\d{9}$")


class QualityRule:
    """Base definition for a data quality rule."""

    def __init__(
        self,
        name: str,
        dimension: str,
        column: str,
        severity: str = "WARNING",
        description: str = "",
    ):
        self.name = name
        self.dimension = dimension
        self.column = column
        self.severity = severity
        self.description = description

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        raise NotImplementedError


class CompletenessRule(QualityRule):
    """Checks that a column has non-null, non-empty, and non-whitespace values."""

    def __init__(
        self,
        name: str,
        column: str,
        severity: str = "WARNING",
        disallowed_literals: set[str] | None = None,
    ):
        super().__init__(
            name=name,
            dimension="Completeness",
            column=column,
            severity=severity,
            description=f"Ensures {column} is populated with valid content",
        )
        self.disallowed_literals = disallowed_literals or {
            "N/A",
            "NA",
            "NULL",
            "NONE",
            "",
        }

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            is_empty = False

            if (
                val is None
                or isinstance(val, str)
                and (
                    val.strip() == "" or val.strip().upper() in self.disallowed_literals
                )
            ):
                is_empty = True

            if is_empty:
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=str(val) if val is not None else "NULL",
                        suggested_value="[REQUIRED]",
                        severity=self.severity,
                    )
                )

        eval_result = RuleEvaluationResult(
            rule_name=self.name,
            dimension=self.dimension,
            column=self.column,
            total_rows=total,
            failed_rows=len(failed_issues),
            severity=self.severity,
        )
        return eval_result, failed_issues


class EmailValidityRule(QualityRule):
    """Validates email format conformance."""

    def __init__(self, name: str = "valid_email_format", column: str = "contact_email"):
        super().__init__(
            name=name,
            dimension="Validity",
            column=column,
            severity="WARNING",
            description="Validates email format syntax and domain validity",
        )

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val).strip()
            if s and (
                not EMAIL_REGEX.match(s) or s.lower() in ("none@domain", "n/a", "na")
            ):
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value="valid_user@domain.com",
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class PhoneValidityRule(QualityRule):
    """Validates phone number conformity to standard Philippine mobile 09XXXXXXXXX."""

    def __init__(self, name: str = "valid_phone_format", column: str = "phone_number"):
        super().__init__(
            name=name,
            dimension="Validity",
            column=column,
            severity="WARNING",
            description="Validates standard Philippine 11-digit mobile phone formatting",
        )

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val).strip()
            if not PHONE_STANDARD_REGEX.match(s):
                # Suggest clean 11-digit mobile
                clean_phone = re.sub(r"[^\d]", "", s)
                if clean_phone.startswith("63"):
                    clean_phone = "0" + clean_phone[2:]
                suggested = clean_phone if len(clean_phone) == 11 else "09XXXXXXXXX"

                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value=suggested,
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class CurrencyFormattingRule(QualityRule):
    """Checks that numerical currency columns are stored cleanly without currency symbols or commas."""

    def __init__(self, name: str, column: str, severity: str = "WARNING"):
        super().__init__(
            name=name,
            dimension="Validity",
            column=column,
            severity=severity,
            description=f"Ensures {column} is stored without currency symbols or commas",
        )

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val)
            if any(c in s for c in ("₱", "PHP", "php", ",")) or " " in s:
                clean_numeric = (
                    s.replace("₱", "")
                    .replace("PHP", "")
                    .replace("php", "")
                    .replace(",", "")
                    .strip()
                )
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value=clean_numeric,
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class DateValidityRule(QualityRule):
    """Validates date format compliance (strict ISO YYYY-MM-DD and real calendar date)."""

    def __init__(self, name: str = "valid_date_format", column: str = "order_date"):
        super().__init__(
            name=name,
            dimension="Validity",
            column=column,
            severity="WARNING",
            description="Validates ISO YYYY-MM-DD calendar date conformance",
        )

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val).strip()
            is_valid = False
            if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
                try:
                    datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
                    is_valid = True
                except ValueError:
                    is_valid = False

            if not is_valid:
                # Attempt best-guess suggestion
                suggested: str | None = None
                if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
                    parts = s.split("/")
                    suggested = f"{parts[2]}-{parts[0]}-{parts[1]}"
                elif re.match(r"^\d{4}\.\d{2}\.\d{2}$", s):
                    suggested = s.replace(".", "-")

                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value=suggested or "YYYY-MM-DD",
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class PositiveQuantityRule(QualityRule):
    """Validates that transaction quantity is non-negative (Critical business check)."""

    def __init__(self, name: str = "positive_quantity", column: str = "quantity"):
        super().__init__(
            name=name,
            dimension="Validity",
            column=column,
            severity="CRITICAL",
            description="Ensures sales transaction quantities are non-negative",
        )

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            try:
                num = float(val)
                if num < 0:
                    failed_issues.append(
                        RuleIssue(
                            row_key=key,
                            column=self.column,
                            rule_name=self.name,
                            dimension=self.dimension,
                            observed_value=str(val),
                            suggested_value=str(abs(num)),
                            severity=self.severity,
                        )
                    )
            except (ValueError, TypeError):
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=str(val),
                        suggested_value="0",
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class CatalogSkuRule(QualityRule):
    """Ensures product SKU belongs to the valid catalog and is not an orphan/unlisted item."""

    def __init__(
        self,
        name: str = "valid_catalog_sku",
        column: str = "sku",
        orphan_skus: set[str] | None = None,
        severity: str = "CRITICAL",
    ):
        super().__init__(
            name=name,
            dimension="Consistency",
            column=column,
            severity=severity,
            description="Ensures SKU corresponds to registered catalog items",
        )
        self.orphan_skus = orphan_skus or KNOWN_ORPHAN_SKUS

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val).strip()
            if s in self.orphan_skus or s.startswith(("UNLISTED-", "OBSOLETE-")):
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value="CATALOG_SKU",
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class UniquenessRule(QualityRule):
    """Validates unique primary key integrity."""

    def __init__(self, name: str, column: str, severity: str = "CRITICAL"):
        super().__init__(
            name=name,
            dimension="Uniqueness",
            column=column,
            severity=severity,
            description=f"Ensures {column} has unique non-duplicate values",
        )

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        seen: set[Any] = set()
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            if val in seen:
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=str(val),
                        suggested_value=f"{val}_unique",
                        severity=self.severity,
                    )
                )
            else:
                seen.add(val)

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class DuplicateEntityVariantRule(QualityRule):
    """Detects entity near-duplicates and variant naming discrepancies."""

    def __init__(
        self,
        name: str = "duplicate_entity_variant",
        column: str = "customer_name",
        known_variants: dict[str, str] | None = None,
    ):
        super().__init__(
            name=name,
            dimension="Uniqueness",
            column=column,
            severity="WARNING",
            description="Identifies near-duplicate company name variants requiring entity resolution",
        )
        self.known_variants = known_variants or CANONICAL_CUSTOMER_ENTITIES

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val).strip()
            if s in self.known_variants:
                canonical = self.known_variants[s]
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value=canonical,
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class WhitespaceCasingRule(QualityRule):
    """Detects inconsistent text casing and padding whitespace."""

    def __init__(self, name: str, column: str, severity: str = "WARNING"):
        super().__init__(
            name=name,
            dimension="Consistency",
            column=column,
            severity=severity,
            description=f"Detects abnormal casing or padding whitespace on {column}",
        )

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val)
            has_whitespace = s != s.strip()
            trimmed = s.strip()
            is_all_upper = (trimmed == trimmed.upper()) and len(trimmed) > 3
            is_all_lower = (trimmed == trimmed.lower()) and len(trimmed) > 3

            if has_whitespace or is_all_upper or is_all_lower:
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value=trimmed.title(),
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


class SpellingVariantRule(QualityRule):
    """Detects spelling, abbreviation, and geographic variance."""

    def __init__(
        self,
        name: str = "spelling_variant",
        column: str = "city",
        spelling_map: dict[str, str] | None = None,
    ):
        super().__init__(
            name=name,
            dimension="Consistency",
            column=column,
            severity="WARNING",
            description="Identifies regional and categorical spelling discrepancies",
        )
        self.spelling_map = spelling_map or CITY_SPELLING_MAP

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        row_key_col: str = "id",
    ) -> tuple[RuleEvaluationResult, list[RuleIssue]]:
        failed_issues: list[RuleIssue] = []
        total = len(rows)

        for row in rows:
            val = row.get(self.column)
            key = str(row.get(row_key_col, ""))
            if val is None:
                continue

            s = str(val)
            if s in self.spelling_map:
                suggested = self.spelling_map[s]
                failed_issues.append(
                    RuleIssue(
                        row_key=key,
                        column=self.column,
                        rule_name=self.name,
                        dimension=self.dimension,
                        observed_value=s,
                        suggested_value=suggested,
                        severity=self.severity,
                    )
                )

        return (
            RuleEvaluationResult(
                rule_name=self.name,
                dimension=self.dimension,
                column=self.column,
                total_rows=total,
                failed_rows=len(failed_issues),
                severity=self.severity,
            ),
            failed_issues,
        )


def get_default_customer_rules() -> list[QualityRule]:
    """Returns standard suite of rules for customers/legacy_customers dataset."""
    return [
        CompletenessRule(
            name="customer_id_completeness",
            column="legacy_customer_id",
            severity="CRITICAL",
        ),
        CompletenessRule(
            name="customer_name_completeness",
            column="customer_name",
            severity="CRITICAL",
        ),
        CompletenessRule(
            name="contact_email_completeness",
            column="contact_email",
            severity="WARNING",
        ),
        EmailValidityRule(name="valid_email_format", column="contact_email"),
        PhoneValidityRule(name="valid_phone_format", column="phone_number"),
        CurrencyFormattingRule(
            name="credit_limit_currency_format", column="credit_limit"
        ),
        UniquenessRule(
            name="unique_legacy_customer_id",
            column="legacy_customer_id",
            severity="CRITICAL",
        ),
        DuplicateEntityVariantRule(
            name="duplicate_entity_variant", column="customer_name"
        ),
        WhitespaceCasingRule(name="city_whitespace_casing", column="city"),
        SpellingVariantRule(name="city_spelling_variant", column="city"),
    ]


def get_default_sales_rules() -> list[QualityRule]:
    """Returns standard suite of rules for sales/legacy_sales dataset."""
    return [
        CompletenessRule(
            name="invoice_no_completeness", column="invoice_no", severity="CRITICAL"
        ),
        UniquenessRule(
            name="unique_invoice_no", column="invoice_no", severity="CRITICAL"
        ),
        DateValidityRule(name="valid_order_date", column="order_date"),
        PositiveQuantityRule(name="positive_quantity", column="quantity"),
        CatalogSkuRule(name="valid_catalog_sku", column="sku", severity="CRITICAL"),
        CurrencyFormattingRule(
            name="total_amount_currency_format", column="total_amount"
        ),
    ]
