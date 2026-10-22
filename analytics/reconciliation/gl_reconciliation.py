"""
General Ledger Reconciliation Engine (Roadmap §V2.5 Capstone-V3)
Validates mathematical and accounting invariants between the OLTP operational
General Ledger (erp_crm) and the OLAP analytical mart (erp_analytics.mart).

Invariants enforced:
1. Operational Double-Entry Parity: SUM(operational debits) == SUM(operational credits).
2. Analytical Mart Parity: SUM(mart debits) == SUM(mart credits).
3. Cross-System Parity: SUM(operational debits) == SUM(mart debits) and
   SUM(operational credits) == SUM(mart credits).
4. Per-Account Balance Parity: For each active account code,
   operational net balance == mart net balance.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, inspect, text

from analytics.db import get_analytics_engine, get_erp_engine


@dataclass
class AccountReconciliationItem:
    account_code: str
    account_name: str
    account_type: str
    operational_debit: Decimal
    operational_credit: Decimal
    operational_balance: Decimal
    mart_debit: Decimal
    mart_credit: Decimal
    mart_balance: Decimal
    variance: Decimal
    is_reconciled: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = float(v)
        return d


@dataclass
class GLReconciliationReport:
    checked_at: str
    as_of_date: str | None
    is_reconciled: bool
    status: str
    operational_debit_total: Decimal
    operational_credit_total: Decimal
    operational_entry_count: int
    operational_line_count: int
    mart_debit_total: Decimal
    mart_credit_total: Decimal
    mart_entry_count: int
    mart_line_count: int
    total_debit_variance: Decimal
    total_credit_variance: Decimal
    net_variance: Decimal
    account_count: int
    discrepant_accounts: list[AccountReconciliationItem] = field(default_factory=list)
    reconciled_accounts_sample: list[AccountReconciliationItem] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "checked_at": self.checked_at,
            "as_of_date": self.as_of_date,
            "is_reconciled": self.is_reconciled,
            "status": self.status,
            "operational_debit_total": float(self.operational_debit_total),
            "operational_credit_total": float(self.operational_credit_total),
            "operational_entry_count": self.operational_entry_count,
            "operational_line_count": self.operational_line_count,
            "mart_debit_total": float(self.mart_debit_total),
            "mart_credit_total": float(self.mart_credit_total),
            "mart_entry_count": self.mart_entry_count,
            "mart_line_count": self.mart_line_count,
            "total_debit_variance": float(self.total_debit_variance),
            "total_credit_variance": float(self.total_credit_variance),
            "net_variance": float(self.net_variance),
            "account_count": self.account_count,
            "discrepant_accounts": [a.to_dict() for a in self.discrepant_accounts],
            "reconciled_accounts_sample": [
                a.to_dict() for a in self.reconciled_accounts_sample
            ],
        }
        return data


class GLReconciler:
    """
    Automated reconciliation auditor verifying integrity between operational GL
    and analytical marts.
    """

    def __init__(
        self,
        erp_engine: Engine | None = None,
        analytics_engine: Engine | None = None,
    ):
        self.erp_engine = erp_engine or get_erp_engine()
        self.analytics_engine = analytics_engine or get_analytics_engine()

    def _resolve_mart_table_names(self) -> tuple[str, str]:
        """Resolves fact and dim table names handling schema prefixing."""
        dialect = self.analytics_engine.dialect.name
        if dialect == "postgresql":
            return "mart.fact_gl_journal_line", "mart.dim_account"
        # SQLite or non-schema databases
        inspector = inspect(self.analytics_engine)
        tables = set(inspector.get_table_names())
        fact = (
            "fact_gl_journal_line"
            if "fact_gl_journal_line" in tables
            else "mart_fact_gl_journal_line"
        )
        dim = "dim_account" if "dim_account" in tables else "mart_dim_account"
        return fact, dim

    def reconcile_totals(self, as_of_date: date | str | None = None) -> dict[str, Any]:
        """
        Calculates aggregate totals from both systems and checks variance.
        """
        as_of_str = str(as_of_date) if as_of_date else None
        fact_table, _ = self._resolve_mart_table_names()

        # Operational query
        op_where = "WHERE je.status = 'posted'"
        params: dict[str, Any] = {}
        if as_of_str:
            op_where += " AND je.posting_date <= :as_of_date"
            params["as_of_date"] = as_of_str

        op_sql = f"""
            SELECT
                COALESCE(SUM(jel.debit_amount), 0) AS total_debit,
                COALESCE(SUM(jel.credit_amount), 0) AS total_credit,
                COUNT(DISTINCT je.id) AS entry_count,
                COUNT(jel.id) AS line_count
            FROM journal_entries je
            JOIN journal_entry_lines jel ON jel.journal_entry_id = je.id
            {op_where}
        """

        with self.erp_engine.connect() as conn:
            op_row = conn.execute(text(op_sql), params).mappings().one()

        op_debit = Decimal(str(op_row["total_debit"]))
        op_credit = Decimal(str(op_row["total_credit"]))
        op_entries = int(op_row["entry_count"] or 0)
        op_lines = int(op_row["line_count"] or 0)

        # Analytical mart query
        mart_where = ""
        mart_params: dict[str, Any] = {}
        if as_of_str:
            mart_where = "WHERE posting_date <= :as_of_date"
            mart_params["as_of_date"] = as_of_str

        mart_sql = f"""
            SELECT
                COALESCE(SUM(debit_amount), 0) AS total_debit,
                COALESCE(SUM(credit_amount), 0) AS total_credit,
                COUNT(DISTINCT journal_entry_id) AS entry_count,
                COUNT(*) AS line_count
            FROM {fact_table}
            {mart_where}
        """

        try:
            with self.analytics_engine.connect() as a_conn:
                mart_row = a_conn.execute(text(mart_sql), mart_params).mappings().one()
            mart_debit = Decimal(str(mart_row["total_debit"]))
            mart_credit = Decimal(str(mart_row["total_credit"]))
            mart_entries = int(mart_row["entry_count"] or 0)
            mart_lines = int(mart_row["line_count"] or 0)
        except Exception:  # noqa: BLE001
            # Fallback if mart is not populated or table doesn't exist
            mart_debit = Decimal("0.00")
            mart_credit = Decimal("0.00")
            mart_entries = 0
            mart_lines = 0

        debit_var = op_debit - mart_debit
        credit_var = op_credit - mart_credit
        net_var = (op_debit - op_credit) - (mart_debit - mart_credit)

        is_reconciled = (
            abs(debit_var) == Decimal("0.00")
            and abs(credit_var) == Decimal("0.00")
            and abs(op_debit - op_credit) == Decimal("0.00")
            and abs(mart_debit - mart_credit) == Decimal("0.00")
        )

        return {
            "operational": {
                "debit": op_debit,
                "credit": op_credit,
                "entries": op_entries,
                "lines": op_lines,
                "balanced": (op_debit == op_credit),
            },
            "mart": {
                "debit": mart_debit,
                "credit": mart_credit,
                "entries": mart_entries,
                "lines": mart_lines,
                "balanced": (mart_debit == mart_credit),
            },
            "variance": {
                "debit_diff": debit_var,
                "credit_diff": credit_var,
                "net_diff": net_var,
            },
            "is_reconciled": is_reconciled,
        }

    def reconcile_accounts(
        self, as_of_date: date | str | None = None
    ) -> list[AccountReconciliationItem]:
        """
        Compares balances on an account-by-account grain between operational GL and analytical mart.
        """
        as_of_str = str(as_of_date) if as_of_date else None
        fact_table, dim_table = self._resolve_mart_table_names()

        # Operational balances by account code
        op_where = "WHERE je.status = 'posted'"
        params: dict[str, Any] = {}
        if as_of_str:
            op_where += " AND je.posting_date <= :as_of_date"
            params["as_of_date"] = as_of_str

        op_sql = f"""
            SELECT
                a.code AS account_code,
                a.name AS account_name,
                a.account_type,
                a.normal_balance,
                COALESCE(SUM(jel.debit_amount), 0) AS total_debit,
                COALESCE(SUM(jel.credit_amount), 0) AS total_credit
            FROM accounts a
            LEFT JOIN journal_entry_lines jel ON jel.account_id = a.id
            LEFT JOIN journal_entries je ON je.id = jel.journal_entry_id AND je.status = 'posted'
            {op_where if as_of_str else ""}
            GROUP BY a.code, a.name, a.account_type, a.normal_balance
            ORDER BY a.code
        """

        with self.erp_engine.connect() as conn:
            op_rows = conn.execute(text(op_sql), params).mappings().all()

        op_map = {row["account_code"]: row for row in op_rows}

        # Mart balances by account code
        mart_where = ""
        mart_params: dict[str, Any] = {}
        if as_of_str:
            mart_where = "WHERE f.posting_date <= :as_of_date"
            mart_params["as_of_date"] = as_of_str

        mart_sql = f"""
            SELECT
                d.account_code,
                COALESCE(SUM(f.debit_amount), 0) AS total_debit,
                COALESCE(SUM(f.credit_amount), 0) AS total_credit
            FROM {dim_table} d
            LEFT JOIN {fact_table} f ON f.account_key = d.account_key
            {mart_where}
            GROUP BY d.account_code
        """

        mart_map: dict[str, Any] = {}
        try:
            with self.analytics_engine.connect() as a_conn:
                m_rows = a_conn.execute(text(mart_sql), mart_params).mappings().all()
            mart_map = {row["account_code"]: row for row in m_rows}
        except Exception:  # noqa: BLE001
            mart_map = {}

        results: list[AccountReconciliationItem] = []

        all_codes = sorted(set(op_map.keys()) | set(mart_map.keys()))
        for code in all_codes:
            op_data = op_map.get(code)
            mart_data = mart_map.get(code)

            name = op_data["account_name"] if op_data else "Unknown"
            acct_type = op_data["account_type"] if op_data else "unknown"
            normal = op_data["normal_balance"] if op_data else "debit"

            op_d = Decimal(str(op_data["total_debit"])) if op_data else Decimal("0.00")
            op_c = Decimal(str(op_data["total_credit"])) if op_data else Decimal("0.00")

            mart_d = (
                Decimal(str(mart_data["total_debit"])) if mart_data else Decimal("0.00")
            )
            mart_c = (
                Decimal(str(mart_data["total_credit"]))
                if mart_data
                else Decimal("0.00")
            )

            if normal == "debit":
                op_bal = op_d - op_c
                mart_bal = mart_d - mart_c
            else:
                op_bal = op_c - op_d
                mart_bal = mart_c - mart_d

            variance = op_bal - mart_bal
            is_rec = (
                (variance == Decimal("0.00")) and (op_d == mart_d) and (op_c == mart_c)
            )

            results.append(
                AccountReconciliationItem(
                    account_code=code,
                    account_name=name,
                    account_type=acct_type,
                    operational_debit=op_d,
                    operational_credit=op_c,
                    operational_balance=op_bal,
                    mart_debit=mart_d,
                    mart_credit=mart_c,
                    mart_balance=mart_bal,
                    variance=variance,
                    is_reconciled=is_rec,
                )
            )

        return results

    def audit(self, as_of_date: date | str | None = None) -> GLReconciliationReport:
        """
        Performs full reconciliation audit and returns a comprehensive report.
        """
        totals = self.reconcile_totals(as_of_date)
        acct_items = self.reconcile_accounts(as_of_date)

        discrepant = [item for item in acct_items if not item.is_reconciled]
        sample = [item for item in acct_items if item.is_reconciled][:5]

        is_reconciled = totals["is_reconciled"] and (len(discrepant) == 0)
        status = "reconciled" if is_reconciled else "discrepant"

        return GLReconciliationReport(
            checked_at=datetime.now(UTC).isoformat(),
            as_of_date=str(as_of_date) if as_of_date else None,
            is_reconciled=is_reconciled,
            status=status,
            operational_debit_total=totals["operational"]["debit"],
            operational_credit_total=totals["operational"]["credit"],
            operational_entry_count=totals["operational"]["entries"],
            operational_line_count=totals["operational"]["lines"],
            mart_debit_total=totals["mart"]["debit"],
            mart_credit_total=totals["mart"]["credit"],
            mart_entry_count=totals["mart"]["entries"],
            mart_line_count=totals["mart"]["lines"],
            total_debit_variance=totals["variance"]["debit_diff"],
            total_credit_variance=totals["variance"]["credit_diff"],
            net_variance=totals["variance"]["net_diff"],
            account_count=len(acct_items),
            discrepant_accounts=discrepant,
            reconciled_accounts_sample=sample,
        )
