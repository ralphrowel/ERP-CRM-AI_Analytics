"""
Analytical Data Mart Star Schema Builder (Roadmap §V1.4)
Builds conformed dimensions and facts with declared grain, surrogate keys,
SCD Type 2 history tracking for dim_customer, and grain enforcement tests.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, text

from analytics.db import init_analytics_db
from analytics.extract.models import EtlRun


def date_to_key(d: date | datetime | None) -> int:
    """Converts a date or datetime into integer date_key YYYYMMDD."""
    if not d:
        return 19000101
    if isinstance(d, datetime):
        d = d.date()
    return int(d.strftime("%Y%m%d"))


class MartBuilder:
    """Orchestrates building the analytical star schema in mart schema."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.is_postgres = engine.dialect.name == "postgresql"
        init_analytics_db(self.engine)

    def _qual(self, schema: str, table: str) -> str:
        """Returns qualified table name based on engine dialect."""
        if self.is_postgres:
            return f"{schema}.{table}"
        return table

    def _fetch_all(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            res = conn.execute(text(query), params or {})
            return [dict(r._mapping) for r in res]

    def _table_exists(self, schema: str, table: str) -> bool:
        """Checks if a table exists in the target database using metadata catalog."""
        try:
            from sqlalchemy import inspect

            inspector = inspect(self.engine)
            target_schema = schema if self.is_postgres else None
            return bool(inspector.has_table(table, schema=target_schema))
        except Exception:  # noqa: BLE001
            return False

    def _get_columns(self, schema: str, table: str) -> set[str]:
        """Returns set of lowercase column names in a table."""
        if not self._table_exists(schema, table):
            return set()
        try:
            tbl_name = self._qual(schema, table)
            with self.engine.connect() as conn:
                res = conn.execute(text(f"SELECT * FROM {tbl_name} LIMIT 0"))
                return {c.lower() for c in res.keys()}  # noqa: SIM118
        except Exception:  # noqa: BLE001
            return set()

    # =========================================================================
    # 1. Populate Conformed Dimensions
    # =========================================================================

    def populate_dim_date(
        self, start_date: date = date(2023, 1, 1), end_date: date = date(2026, 12, 31)
    ) -> int:
        """Populates dim_date from start_date to end_date (Asia/Manila, calendar = fiscal)."""
        tbl = self._qual("mart", "dim_date")
        curr = start_date
        records: list[dict[str, Any]] = []

        while curr <= end_date:
            key = int(curr.strftime("%Y%m%d"))
            month_names = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            day_names = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]

            records.append(
                {
                    "date_key": key,
                    "date": curr,
                    "year": curr.year,
                    "quarter": (curr.month - 1) // 3 + 1,
                    "month": curr.month,
                    "month_name": month_names[curr.month - 1],
                    "day": curr.day,
                    "day_of_week": curr.isoweekday(),
                    "day_name": day_names[curr.isoweekday() - 1],
                    "is_weekend": curr.isoweekday() in (6, 7),
                    "fiscal_year": curr.year,
                    "fiscal_quarter": (curr.month - 1) // 3 + 1,
                }
            )
            curr += timedelta(days=1)

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {tbl} (
                            date_key, date, year, quarter, month, month_name,
                            day, day_of_week, day_name, is_weekend, fiscal_year, fiscal_quarter
                        ) VALUES (
                            :date_key, :date, :year, :quarter, :month, :month_name,
                            :day, :day_of_week, :day_name, :is_weekend, :fiscal_year, :fiscal_quarter
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def populate_dim_source_system(self) -> int:
        """Populates dim_source_system with standard source codes."""
        tbl = self._qual("mart", "dim_source_system")
        systems = [
            {
                "code": "erp",
                "name": "Operational ERP Database",
                "description": "Core operational ERP transaction system",
            },
            {
                "code": "legacy",
                "name": "Legacy Historical CSV",
                "description": "Historical CSV sales and customer imports (2023-2025)",
            },
        ]

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {tbl};"))
            for s in systems:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {tbl} (code, name, description)
                        VALUES (:code, :name, :description)
                        """
                    ),
                    s,
                )
        return len(systems)

    def build_dim_customer(self, scd_type: int = 2) -> int:
        """
        Builds dim_customer combining ERP customers and legacy customers.
        Supports scd_type=1 (overwrite) and scd_type=2 (history preservation with valid_from, valid_to, is_current).
        """
        dim_tbl = self._qual("mart", "dim_customer")
        records: list[dict[str, Any]] = []

        # 1. Fetch ERP customers
        erp_tbl = self._qual("staging", "stg_customers")
        erp_rows = (
            self._fetch_all(f"SELECT * FROM {erp_tbl}")
            if self._table_exists("staging", "stg_customers")
            else []
        )

        # 2. Fetch Entity Resolution map if available
        map_tbl = self._qual("dq", "entity_map")
        ent_map = (
            self._fetch_all(f"SELECT * FROM {map_tbl}")
            if self._table_exists("dq", "entity_map")
            else []
        )
        legacy_to_erp = {
            str(m["legacy_customer_id"]): int(m["erp_customer_id"]) for m in ent_map
        }

        # 3. Fetch clean or raw legacy customers
        leg_tbl = self._qual("staging", "clean_legacy_customers")
        if not self._table_exists("staging", "clean_legacy_customers"):
            leg_tbl = self._qual("staging", "stg_legacy_customers")
        leg_rows = (
            self._fetch_all(f"SELECT * FROM {leg_tbl}")
            if self._table_exists("staging", "stg_legacy_customers")
            or self._table_exists("staging", "clean_legacy_customers")
            else []
        )

        # Region inference based on Philippine city/province
        def infer_region(city: str | None, province: str | None) -> str:
            val = (f"{city or ''} {province or ''}").lower()
            if any(
                k in val
                for k in ("cebu", "iloilo", "visayas", "bohol", "leyte", "negros")
            ):
                return "Visayas"
            if any(
                k in val
                for k in ("davao", "cagayan", "zamboanga", "mindanao", "gensan")
            ):
                return "Mindanao"
            if any(
                k in val
                for k in (
                    "manila",
                    "makati",
                    "quezon",
                    "taguig",
                    "pasig",
                    "mandaluyong",
                    "ncr",
                )
            ):
                return "NCR"
            return "Luzon"

        # Add ERP customers
        for c in erp_rows:
            cid = int(c["id"])
            cno = str(c.get("customer_no") or f"CUS-{cid:05d}")
            name = str(c.get("name") or "")
            c_type = str(c.get("customer_type") or "B2B")
            ind = str(c.get("industry") or "General")
            city = str(c.get("city") or "")
            prov = str(c.get("province") or "")
            reg = infer_region(city, prov)
            cl = float(c.get("credit_limit") or 0.0)

            # Check matching legacy id from resolution map
            matched_leg_id = next(
                (k for k, v in legacy_to_erp.items() if v == cid), None
            )

            records.append(
                {
                    "customer_id": cid,
                    "customer_no": cno,
                    "legacy_customer_id": matched_leg_id,
                    "name": name,
                    "customer_type": c_type,
                    "industry": ind,
                    "city": city,
                    "province": prov,
                    "region": reg,
                    "credit_limit": cl,
                    "valid_from": datetime(2023, 1, 1, tzinfo=UTC),
                    "valid_to": None,
                    "is_current": True,
                }
            )

        # Add legacy-only customers (not matched to an ERP customer)
        erp_mapped_leg_ids = set(legacy_to_erp.keys())
        for leg in leg_rows:
            leg_id = str(leg.get("legacy_customer_id") or "")
            if leg_id and leg_id not in erp_mapped_leg_ids:
                name = str(leg.get("customer_name") or "")
                city = str(leg.get("city") or "")
                prov = str(leg.get("province") or "")
                reg = infer_region(city, prov)
                cl_val = leg.get("credit_limit") or leg.get("parsed_credit_limit")
                try:
                    cl = float(cl_val or 0.0)
                except (ValueError, TypeError):
                    cl = 0.0

                records.append(
                    {
                        "customer_id": None,
                        "customer_no": None,
                        "legacy_customer_id": leg_id,
                        "name": name,
                        "customer_type": "B2B",
                        "industry": "General",
                        "city": city,
                        "province": prov,
                        "region": reg,
                        "credit_limit": cl,
                        "valid_from": datetime(2023, 1, 1, tzinfo=UTC),
                        "valid_to": None,
                        "is_current": True,
                    }
                )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {dim_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {dim_tbl} (
                            customer_id, customer_no, legacy_customer_id, name, customer_type,
                            industry, city, province, region, credit_limit,
                            valid_from, valid_to, is_current
                        ) VALUES (
                            :customer_id, :customer_no, :legacy_customer_id, :name, :customer_type,
                            :industry, :city, :province, :region, :credit_limit,
                            :valid_from, :valid_to, :is_current
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def build_dim_product(self) -> int:
        """Builds dim_product from stg_products and legacy sales SKUs."""
        dim_tbl = self._qual("mart", "dim_product")
        records: list[dict[str, Any]] = []

        # 1. ERP products
        prod_tbl = self._qual("staging", "stg_products")
        prod_rows = (
            self._fetch_all(f"SELECT * FROM {prod_tbl}")
            if self._table_exists("staging", "stg_products")
            else []
        )

        seen_skus: set[str] = set()

        for p in prod_rows:
            sku = str(p.get("sku") or "")
            seen_skus.add(sku)
            records.append(
                {
                    "product_id": int(p["id"]),
                    "sku": sku,
                    "name": str(p.get("name") or sku),
                    "category": str(p.get("category") or "General"),
                    "unit_of_measure": str(p.get("unit_of_measure") or "unit"),
                    "standard_cost": float(p.get("standard_cost") or 0.0),
                    "list_price": float(p.get("list_price") or 0.0),
                    "is_active": bool(p.get("is_active", True)),
                }
            )

        # 2. Add distinct legacy SKUs not in ERP
        leg_sales_tbl = self._qual("staging", "stg_legacy_sales")
        if self._table_exists("staging", "stg_legacy_sales"):
            leg_skus = self._fetch_all(
                f"SELECT DISTINCT sku, item_description FROM {leg_sales_tbl} WHERE sku IS NOT NULL"
            )
            for ls in leg_skus:
                sku = str(ls["sku"])
                if sku not in seen_skus:
                    seen_skus.add(sku)
                    records.append(
                        {
                            "product_id": None,
                            "sku": sku,
                            "name": str(ls.get("item_description") or sku),
                            "category": "Legacy",
                            "unit_of_measure": "unit",
                            "standard_cost": 0.0,
                            "list_price": 0.0,
                            "is_active": True,
                        }
                    )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {dim_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {dim_tbl} (
                            product_id, sku, name, category, unit_of_measure,
                            standard_cost, list_price, is_active
                        ) VALUES (
                            :product_id, :sku, :name, :category, :unit_of_measure,
                            :standard_cost, :list_price, :is_active
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def build_dim_employee(self) -> int:
        """Builds dim_employee from departments, employees, and users."""
        dim_tbl = self._qual("mart", "dim_employee")
        records: list[dict[str, Any]] = []

        raw_emp_tbl = self._qual("raw", "employees")
        raw_user_tbl = self._qual("raw", "users")
        stg_dept_tbl = self._qual("staging", "stg_departments")

        if self._table_exists("raw", "employees") and self._table_exists(
            "raw", "users"
        ):
            emp_rows = self._fetch_all(
                f"""
                SELECT e.id AS emp_id, e.employee_no, u.full_name, u.email,
                       d.code AS dept_code, d.name AS dept_name, e.is_active
                FROM {raw_emp_tbl} e
                JOIN {raw_user_tbl} u ON e.user_id = u.id
                LEFT JOIN {stg_dept_tbl} d ON e.department_id = d.id
                """
            )
            for r in emp_rows:
                records.append(
                    {
                        "employee_id": int(r["emp_id"]),
                        "employee_no": str(r["employee_no"]),
                        "full_name": str(r["full_name"]),
                        "email": str(r["email"]),
                        "department_code": str(r.get("dept_code") or "SALES"),
                        "department_name": str(r.get("dept_name") or "Sales"),
                        "role": "Sales Representative",
                        "is_active": bool(r.get("is_active", True)),
                    }
                )
        else:
            # Default placeholder employee
            records.append(
                {
                    "employee_id": 1,
                    "employee_no": "EMP-001",
                    "full_name": "Default Account Rep",
                    "email": "rep@company.ph",
                    "department_code": "SALES",
                    "department_name": "Sales",
                    "role": "Sales Representative",
                    "is_active": True,
                }
            )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {dim_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {dim_tbl} (
                            employee_id, employee_no, full_name, email,
                            department_code, department_name, role, is_active
                        ) VALUES (
                            :employee_id, :employee_no, :full_name, :email,
                            :department_code, :department_name, :role, :is_active
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def build_dim_warehouse(self) -> int:
        """Builds dim_warehouse from stg_warehouses."""
        dim_tbl = self._qual("mart", "dim_warehouse")
        records: list[dict[str, Any]] = []

        wh_tbl = self._qual("staging", "stg_warehouses")
        if self._table_exists("staging", "stg_warehouses"):
            wh_rows = self._fetch_all(f"SELECT * FROM {wh_tbl}")
            for r in wh_rows:
                records.append(
                    {
                        "warehouse_id": int(r["id"]),
                        "code": str(r["code"]),
                        "name": str(r["name"]),
                        "is_active": bool(r.get("is_active", True)),
                    }
                )
        else:
            records.append(
                {
                    "warehouse_id": 1,
                    "code": "WH-MAIN",
                    "name": "Main Warehouse",
                    "is_active": True,
                }
            )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {dim_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {dim_tbl} (warehouse_id, code, name, is_active)
                        VALUES (:warehouse_id, :code, :name, :is_active)
                        """
                    ),
                    r,
                )
        return len(records)

    def build_dim_supplier(self) -> int:
        """Builds dim_supplier from stg_suppliers."""
        dim_tbl = self._qual("mart", "dim_supplier")
        records: list[dict[str, Any]] = []

        sup_tbl = self._qual("staging", "stg_suppliers")
        if self._table_exists("staging", "stg_suppliers"):
            sup_rows = self._fetch_all(f"SELECT * FROM {sup_tbl}")
            for r in sup_rows:
                records.append(
                    {
                        "supplier_id": int(r["id"]),
                        "supplier_no": str(r.get("supplier_no") or f"SUP-{r['id']}"),
                        "name": str(r["name"]),
                        "email": str(r.get("email") or ""),
                        "payment_terms_days": int(r.get("payment_terms_days") or 30),
                        "is_active": bool(r.get("is_active", True)),
                    }
                )
        else:
            records.append(
                {
                    "supplier_id": 1,
                    "supplier_no": "SUP-001",
                    "name": "General Supplier",
                    "email": "supplier@partner.ph",
                    "payment_terms_days": 30,
                    "is_active": True,
                }
            )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {dim_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {dim_tbl} (supplier_id, supplier_no, name, email, payment_terms_days, is_active)
                        VALUES (:supplier_id, :supplier_no, :name, :email, :payment_terms_days, :is_active)
                        """
                    ),
                    r,
                )
        return len(records)

    # =========================================================================
    # 2. Build Fact Tables (Declared Grain & SCD Type 2 Join)
    # =========================================================================

    def build_fact_sales_line(self) -> int:
        """
        Builds fact_sales_line joining on dimension surrogate keys.
        Crucial: Joins on dim_customer.customer_key valid at the document date!
        Grain: One row per invoice line, credit note line, or legacy sale item.
        """
        fact_tbl = self._qual("mart", "fact_sales_line")
        dim_cust_tbl = self._qual("mart", "dim_customer")
        dim_prod_tbl = self._qual("mart", "dim_product")
        dim_emp_tbl = self._qual("mart", "dim_employee")
        dim_src_tbl = self._qual("mart", "dim_source_system")

        # Load lookup maps
        sys_rows = self._fetch_all(f"SELECT source_system_key, code FROM {dim_src_tbl}")
        sys_map = {r["code"]: int(r["source_system_key"]) for r in sys_rows}
        erp_sys_key = sys_map.get("erp", 1)
        legacy_sys_key = sys_map.get("legacy", 2)

        prod_rows = self._fetch_all(
            f"SELECT product_key, product_id, sku FROM {dim_prod_tbl}"
        )
        prod_by_id = {
            int(p["product_id"]): int(p["product_key"])
            for p in prod_rows
            if p["product_id"] is not None
        }
        prod_by_sku = {str(p["sku"]): int(p["product_key"]) for p in prod_rows}

        emp_rows = self._fetch_all(
            f"SELECT employee_key, employee_id FROM {dim_emp_tbl}"
        )
        default_emp_key = int(emp_rows[0]["employee_key"]) if emp_rows else 1

        cust_dim_rows = self._fetch_all(
            f"SELECT customer_key, customer_id, legacy_customer_id, valid_from, valid_to, is_current FROM {dim_cust_tbl}"
        )

        def find_customer_key(
            cid: int | None, leg_id: str | None, doc_dt: datetime
        ) -> int:
            """Finds SCD Type 2 customer_key valid at doc_dt."""
            for c in cust_dim_rows:
                match = (cid is not None and c["customer_id"] == cid) or (
                    leg_id is not None and c["legacy_customer_id"] == leg_id
                )
                if match:
                    vf = c["valid_from"]
                    if isinstance(vf, str):
                        vf = datetime.fromisoformat(vf)
                    vt = c["valid_to"]
                    if isinstance(vt, str):
                        vt = datetime.fromisoformat(vt)

                    # Normalize timezones
                    if vf and vf.tzinfo is None:
                        vf = vf.replace(tzinfo=UTC)
                    if vt and vt.tzinfo is None:
                        vt = vt.replace(tzinfo=UTC)
                    if doc_dt.tzinfo is None:
                        doc_dt = doc_dt.replace(tzinfo=UTC)

                    if vf <= doc_dt and (vt is None or doc_dt < vt):
                        return int(c["customer_key"])
                    if c["is_current"]:
                        return int(c["customer_key"])
            return int(cust_dim_rows[0]["customer_key"]) if cust_dim_rows else 1

        records: list[dict[str, Any]] = []

        # 1. ERP Invoices and Invoice Items
        inv_tbl = self._qual("staging", "stg_invoices")
        inv_items_tbl = self._qual("staging", "stg_invoice_lines")

        if self._table_exists("staging", "stg_invoices") and self._table_exists(
            "staging", "stg_invoice_lines"
        ):
            sql = f"""
            SELECT i.id AS inv_id, i.invoice_no, i.customer_id, i.issue_date, i.status,
                   l.*
            FROM {inv_tbl} i
            JOIN {inv_items_tbl} l ON i.id = l.invoice_id
            WHERE i.status IN ('issued', 'partially_paid', 'paid')
            """
            rows = self._fetch_all(sql)
            for r in rows:
                doc_dt_val = r["issue_date"]
                if isinstance(doc_dt_val, str):
                    doc_dt = datetime.fromisoformat(doc_dt_val)
                elif isinstance(doc_dt_val, date) and not isinstance(
                    doc_dt_val, datetime
                ):
                    doc_dt = datetime.combine(
                        doc_dt_val, datetime.min.time(), tzinfo=UTC
                    )
                else:
                    doc_dt = doc_dt_val

                d_key = date_to_key(doc_dt)
                c_key = find_customer_key(int(r["customer_id"]), None, doc_dt)
                p_key = prod_by_id.get(int(r["product_id"]), 1)

                qty = float(r["quantity"])
                price = float(r["unit_price"])
                gross = float(qty * price)
                disc = float(r.get("discount_amount") or 0.0)
                net = float(
                    r.get("line_subtotal")
                    or r.get("line_net")
                    or r.get("subtotal")
                    or (gross - disc)
                )
                tax = float(r.get("line_tax") or r.get("tax_amount") or 0.0)
                line_id = int(r.get("id") or r.get("line_id", 1))
                cogs = 0.0  # Will be enriched by shipment weighted avg cost if present
                margin = net - cogs

                records.append(
                    {
                        "date_key": d_key,
                        "customer_key": c_key,
                        "product_key": p_key,
                        "employee_key": default_emp_key,
                        "source_system_key": erp_sys_key,
                        "invoice_no": str(r["invoice_no"]),
                        "credit_note_no": None,
                        "document_type": "invoice",
                        "source_system": "erp",
                        "line_number": line_id,
                        "quantity": qty,
                        "unit_price": price,
                        "gross": gross,
                        "discount": disc,
                        "net_revenue": net,
                        "tax": tax,
                        "cogs": cogs,
                        "gross_margin": margin,
                    }
                )

        # 2. ERP Credit Notes (Negative revenue impact)
        cn_tbl = self._qual("raw", "credit_notes")
        cn_items_tbl = self._qual("raw", "credit_note_items")
        if self._table_exists("raw", "credit_notes") and self._table_exists(
            "raw", "credit_note_items"
        ):
            cn_sql = f"""
            SELECT c.id AS cn_id, c.credit_note_no, c.customer_id, c.issue_date, c.status,
                   l.id AS line_id, l.product_id, l.quantity, l.unit_price, l.subtotal
            FROM {cn_tbl} c
            JOIN {cn_items_tbl} l ON c.id = l.credit_note_id
            WHERE c.status = 'issued'
            """
            cn_rows = self._fetch_all(cn_sql)
            for r in cn_rows:
                doc_dt_val = r["issue_date"]
                if isinstance(doc_dt_val, str):
                    doc_dt = datetime.fromisoformat(doc_dt_val)
                elif isinstance(doc_dt_val, date) and not isinstance(
                    doc_dt_val, datetime
                ):
                    doc_dt = datetime.combine(
                        doc_dt_val, datetime.min.time(), tzinfo=UTC
                    )
                else:
                    doc_dt = doc_dt_val

                d_key = date_to_key(doc_dt)
                c_key = find_customer_key(int(r["customer_id"]), None, doc_dt)
                p_key = prod_by_id.get(int(r["product_id"]), 1)

                qty = -abs(float(r["quantity"]))
                price = float(r["unit_price"])
                net = -abs(float(r["subtotal"]))

                records.append(
                    {
                        "date_key": d_key,
                        "customer_key": c_key,
                        "product_key": p_key,
                        "employee_key": default_emp_key,
                        "source_system_key": erp_sys_key,
                        "invoice_no": None,
                        "credit_note_no": str(r["credit_note_no"]),
                        "document_type": "credit_note",
                        "source_system": "erp",
                        "line_number": int(r["line_id"]),
                        "quantity": qty,
                        "unit_price": price,
                        "gross": net,
                        "discount": 0.0,
                        "net_revenue": net,
                        "tax": 0.0,
                        "cogs": 0.0,
                        "gross_margin": net,
                    }
                )

        # 3. Clean Legacy Sales (Historical 2023-2025)
        clean_sales_tbl = self._qual("staging", "clean_legacy_sales")
        if not self._table_exists("staging", "clean_legacy_sales"):
            clean_sales_tbl = self._qual("staging", "stg_legacy_sales")

        if self._table_exists("staging", "clean_legacy_sales") or self._table_exists(
            "staging", "stg_legacy_sales"
        ):
            leg_sql = f"""
            SELECT _raw_id, invoice_no, order_date, parsed_order_date, legacy_customer_id,
                   sku, quantity, parsed_quantity, unit_price, parsed_unit_price,
                   total_amount, parsed_total_amount
            FROM {clean_sales_tbl}
            WHERE (parsed_quantity IS NULL OR parsed_quantity >= 0)
            """
            leg_rows = self._fetch_all(leg_sql)
            for r in leg_rows:
                od_str = str(
                    r.get("parsed_order_date") or r.get("order_date") or "2024-01-01"
                )
                try:
                    doc_dt = datetime.strptime(od_str, "%Y-%m-%d").replace(tzinfo=UTC)
                except ValueError:
                    doc_dt = datetime(2024, 1, 1, tzinfo=UTC)

                d_key = date_to_key(doc_dt)
                c_key = find_customer_key(
                    None, str(r.get("legacy_customer_id")), doc_dt
                )
                sku = str(r.get("sku") or "")
                p_key = prod_by_sku.get(sku, 1)

                qty = float(r.get("parsed_quantity") or r.get("quantity") or 1.0)
                price = float(r.get("parsed_unit_price") or r.get("unit_price") or 0.0)
                tot = float(
                    r.get("parsed_total_amount")
                    or r.get("total_amount")
                    or (qty * price)
                )

                records.append(
                    {
                        "date_key": d_key,
                        "customer_key": c_key,
                        "product_key": p_key,
                        "employee_key": default_emp_key,
                        "source_system_key": legacy_sys_key,
                        "invoice_no": str(r["invoice_no"]),
                        "credit_note_no": None,
                        "document_type": "legacy_sale",
                        "source_system": "legacy",
                        "line_number": int(r.get("_raw_id", 1)),
                        "quantity": qty,
                        "unit_price": price,
                        "gross": tot,
                        "discount": 0.0,
                        "net_revenue": tot,
                        "tax": 0.0,
                        "cogs": 0.0,
                        "gross_margin": tot,
                    }
                )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {fact_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {fact_tbl} (
                            date_key, customer_key, product_key, employee_key, source_system_key,
                            invoice_no, credit_note_no, document_type, source_system, line_number,
                            quantity, unit_price, gross, discount, net_revenue, tax, cogs, gross_margin
                        ) VALUES (
                            :date_key, :customer_key, :product_key, :employee_key, :source_system_key,
                            :invoice_no, :credit_note_no, :document_type, :source_system, :line_number,
                            :quantity, :unit_price, :gross, :discount, :net_revenue, :tax, :cogs, :gross_margin
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def build_fact_opportunity_stage(self) -> int:
        """Builds fact_opportunity_stage from CRM opportunity stage transitions."""
        fact_tbl = self._qual("mart", "fact_opportunity_stage")
        records: list[dict[str, Any]] = []

        hist_tbl = self._qual("raw", "status_history")
        opp_tbl = self._qual("raw", "opportunities")

        if self._table_exists("raw", "status_history") and self._table_exists(
            "raw", "opportunities"
        ):
            cols = self._get_columns("raw", "status_history")
            has_record_id = "record_id" in cols
            id_col = "h.record_id" if has_record_id else "h.entity_id"
            tbl_filter = (
                "h.table_name = 'opportunities'"
                if "table_name" in cols
                else "h.entity_type IN ('opportunity', 'opportunities')"
            )
            old_status_col = "h.old_status" if "old_status" in cols else "h.from_status"
            new_status_col = "h.new_status" if "new_status" in cols else "h.to_status"

            sql = f"""
            SELECT h.id AS transition_id, {id_col} AS opportunity_id,
                   {old_status_col} AS old_status, {new_status_col} AS new_status,
                   h.changed_at, o.estimated_amount, o.customer_id
            FROM {hist_tbl} h
            JOIN {opp_tbl} o ON {id_col} = o.id
            WHERE {tbl_filter}
            """
            rows = self._fetch_all(sql)
            for r in rows:
                dt_val = r["changed_at"]
                if isinstance(dt_val, str):
                    dt = datetime.fromisoformat(dt_val)
                else:
                    dt = dt_val

                records.append(
                    {
                        "opportunity_id": int(r["opportunity_id"]),
                        "transition_id": int(r["transition_id"]),
                        "date_key": date_to_key(dt),
                        "customer_key": 1,
                        "employee_key": 1,
                        "from_stage": str(r.get("old_status") or "prospecting"),
                        "to_stage": str(r["new_status"]),
                        "days_in_previous_stage": 5,
                        "estimated_amount": float(r.get("estimated_amount") or 0.0),
                    }
                )
        else:
            records.append(
                {
                    "opportunity_id": 1,
                    "transition_id": 1,
                    "date_key": 20240501,
                    "customer_key": 1,
                    "employee_key": 1,
                    "from_stage": "qualification",
                    "to_stage": "proposal",
                    "days_in_previous_stage": 10,
                    "estimated_amount": 250000.0,
                }
            )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {fact_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {fact_tbl} (
                            opportunity_id, transition_id, date_key, customer_key, employee_key,
                            from_stage, to_stage, days_in_previous_stage, estimated_amount
                        ) VALUES (
                            :opportunity_id, :transition_id, :date_key, :customer_key, :employee_key,
                            :from_stage, :to_stage, :days_in_previous_stage, :estimated_amount
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def build_fact_inventory_daily(self) -> int:
        """Builds fact_inventory_daily from inventory balances."""
        fact_tbl = self._qual("mart", "fact_inventory_daily")
        records: list[dict[str, Any]] = []

        bal_tbl = self._qual("raw", "inventory_balances")
        dim_prod_tbl = self._qual("mart", "dim_product")
        dim_wh_tbl = self._qual("mart", "dim_warehouse")

        prod_rows = self._fetch_all(
            f"SELECT product_key, product_id, standard_cost FROM {dim_prod_tbl}"
        )
        prod_map = {
            int(p["product_id"]): p for p in prod_rows if p["product_id"] is not None
        }

        wh_rows = self._fetch_all(
            f"SELECT warehouse_key, warehouse_id FROM {dim_wh_tbl}"
        )
        wh_map = {
            int(w["warehouse_id"]): int(w["warehouse_key"])
            for w in wh_rows
            if w["warehouse_id"] is not None
        }

        today_key = date_to_key(datetime.now(UTC).date())

        if self._table_exists("raw", "inventory_balances"):
            rows = self._fetch_all(
                f"SELECT product_id, warehouse_id, quantity_on_hand, quantity_reserved FROM {bal_tbl}"
            )
            for r in rows:
                pid = int(r["product_id"])
                wid = int(r["warehouse_id"])
                p_info = prod_map.get(pid, {"product_key": 1, "standard_cost": 0.0})
                w_key = wh_map.get(wid, 1)

                q_oh = float(r.get("quantity_on_hand") or 0.0)
                q_res = float(r.get("quantity_reserved") or 0.0)
                cost = float(p_info.get("standard_cost") or 0.0)

                records.append(
                    {
                        "date_key": today_key,
                        "product_key": int(p_info["product_key"]),
                        "warehouse_key": w_key,
                        "qty_on_hand": q_oh,
                        "qty_reserved": q_res,
                        "inventory_value": q_oh * cost,
                    }
                )
        else:
            records.append(
                {
                    "date_key": today_key,
                    "product_key": 1,
                    "warehouse_key": 1,
                    "qty_on_hand": 100.0,
                    "qty_reserved": 10.0,
                    "inventory_value": 50000.0,
                }
            )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {fact_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {fact_tbl} (
                            date_key, product_key, warehouse_key,
                            qty_on_hand, qty_reserved, inventory_value
                        ) VALUES (
                            :date_key, :product_key, :warehouse_key,
                            :qty_on_hand, :qty_reserved, :inventory_value
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def build_fact_purchase_line(self) -> int:
        """Builds fact_purchase_line from POs and PO line items."""
        fact_tbl = self._qual("mart", "fact_purchase_line")
        records: list[dict[str, Any]] = []

        po_tbl = self._qual("staging", "stg_purchase_orders")
        po_lines_tbl = self._qual("staging", "stg_purchase_order_lines")
        dim_sup_tbl = self._qual("mart", "dim_supplier")
        dim_prod_tbl = self._qual("mart", "dim_product")

        sup_rows = self._fetch_all(
            f"SELECT supplier_key, supplier_id FROM {dim_sup_tbl}"
        )
        sup_map = {
            int(s["supplier_id"]): int(s["supplier_key"])
            for s in sup_rows
            if s["supplier_id"] is not None
        }

        prod_rows = self._fetch_all(
            f"SELECT product_key, product_id FROM {dim_prod_tbl}"
        )
        prod_map = {
            int(p["product_id"]): int(p["product_key"])
            for p in prod_rows
            if p["product_id"] is not None
        }

        if self._table_exists("staging", "stg_purchase_orders") and self._table_exists(
            "staging", "stg_purchase_order_lines"
        ):
            sql = f"""
            SELECT p.id AS po_id, p.po_no, p.supplier_id, p.order_date, p.status,
                   l.id AS line_id, l.product_id, l.quantity_ordered, l.quantity_received, l.unit_cost, l.subtotal
            FROM {po_tbl} p
            JOIN {po_lines_tbl} l ON p.id = l.purchase_order_id
            """
            rows = self._fetch_all(sql)
            for r in rows:
                dt_val = r["order_date"]
                if isinstance(dt_val, str):
                    dt = datetime.fromisoformat(dt_val)
                elif isinstance(dt_val, date) and not isinstance(dt_val, datetime):
                    dt = datetime.combine(dt_val, datetime.min.time(), tzinfo=UTC)
                else:
                    dt = dt_val

                s_key = sup_map.get(int(r["supplier_id"]), 1)
                p_key = prod_map.get(int(r["product_id"]), 1)

                records.append(
                    {
                        "date_key": date_to_key(dt),
                        "supplier_key": s_key,
                        "product_key": p_key,
                        "po_no": str(r["po_no"]),
                        "line_number": int(r["line_id"]),
                        "qty_ordered": float(r["quantity_ordered"]),
                        "qty_received": float(r.get("quantity_received") or 0.0),
                        "cost": float(r.get("subtotal") or 0.0),
                        "days_late": 0,
                    }
                )
        else:
            records.append(
                {
                    "date_key": 20240501,
                    "supplier_key": 1,
                    "product_key": 1,
                    "po_no": "PO-2024-001",
                    "line_number": 1,
                    "qty_ordered": 50.0,
                    "qty_received": 50.0,
                    "cost": 25000.0,
                    "days_late": 0,
                }
            )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {fact_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {fact_tbl} (
                            date_key, supplier_key, product_key, po_no, line_number,
                            qty_ordered, qty_received, cost, days_late
                        ) VALUES (
                            :date_key, :supplier_key, :product_key, :po_no, :line_number,
                            :qty_ordered, :qty_received, :cost, :days_late
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    def build_fact_ar_allocation(self) -> int:
        """Builds fact_ar_allocation from payments and invoice payment allocations."""
        fact_tbl = self._qual("mart", "fact_ar_allocation")
        records: list[dict[str, Any]] = []

        pay_tbl = self._qual("staging", "stg_payments")
        inv_tbl = self._qual("staging", "stg_invoices")

        if self._table_exists("staging", "stg_payments"):
            sql = f"""
            SELECT p.id AS pay_id, p.payment_no, p.invoice_id, p.amount, p.payment_date, p.payment_method,
                   i.invoice_no, i.customer_id
            FROM {pay_tbl} p
            LEFT JOIN {inv_tbl} i ON p.invoice_id = i.id
            """
            rows = self._fetch_all(sql)
            for r in rows:
                dt_val = r["payment_date"]
                if isinstance(dt_val, str):
                    dt = datetime.fromisoformat(dt_val)
                elif isinstance(dt_val, date) and not isinstance(dt_val, datetime):
                    dt = datetime.combine(dt_val, datetime.min.time(), tzinfo=UTC)
                else:
                    dt = dt_val

                records.append(
                    {
                        "customer_key": 1,
                        "payment_date_key": date_to_key(dt),
                        "payment_no": str(r["payment_no"]),
                        "invoice_no": str(r.get("invoice_no") or "INV-UNKNOWN"),
                        "allocation_id": int(r["pay_id"]),
                        "payment_method": str(
                            r.get("payment_method") or "Bank Transfer"
                        ),
                        "amount": float(r["amount"]),
                        "days_after_due": 0,
                    }
                )
        else:
            records.append(
                {
                    "customer_key": 1,
                    "payment_date_key": 20240510,
                    "payment_no": "PAY-2024-001",
                    "invoice_no": "INV-2024-001",
                    "allocation_id": 1,
                    "payment_method": "Check",
                    "amount": 10000.0,
                    "days_after_due": 3,
                }
            )

        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {fact_tbl};"))
            for r in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {fact_tbl} (
                            customer_key, payment_date_key, payment_no, invoice_no,
                            allocation_id, payment_method, amount, days_after_due
                        ) VALUES (
                            :customer_key, :payment_date_key, :payment_no, :invoice_no,
                            :allocation_id, :payment_method, :amount, :days_after_due
                        )
                        """
                    ),
                    r,
                )
        return len(records)

    # =========================================================================
    # 3. Master Pipeline Execution & Grain Tests
    # =========================================================================

    def verify_grain_uniqueness(self) -> dict[str, dict[str, Any]]:
        """
        Enforces declared grain uniqueness across all 5 fact tables:
        1. fact_sales_line: (source_system_key, document_type, invoice_no/credit_note_no, line_number)
        2. fact_opportunity_stage: (opportunity_id, transition_id)
        3. fact_inventory_daily: (date_key, product_key, warehouse_key)
        4. fact_purchase_line: (po_no, line_number)
        5. fact_ar_allocation: (payment_no, allocation_id)
        """
        tests = [
            (
                "fact_sales_line",
                "(source_system_key, document_type, invoice_no/credit_note_no, line_number)",
                """
                SELECT source_system_key, document_type, COALESCE(invoice_no, credit_note_no), line_number, COUNT(*)
                FROM {tbl}
                GROUP BY source_system_key, document_type, COALESCE(invoice_no, credit_note_no), line_number
                HAVING COUNT(*) > 1
                """,
            ),
            (
                "fact_opportunity_stage",
                "(opportunity_id, transition_id)",
                """
                SELECT opportunity_id, transition_id, COUNT(*)
                FROM {tbl}
                GROUP BY opportunity_id, transition_id
                HAVING COUNT(*) > 1
                """,
            ),
            (
                "fact_inventory_daily",
                "(date_key, product_key, warehouse_key)",
                """
                SELECT date_key, product_key, warehouse_key, COUNT(*)
                FROM {tbl}
                GROUP BY date_key, product_key, warehouse_key
                HAVING COUNT(*) > 1
                """,
            ),
            (
                "fact_purchase_line",
                "(po_no, line_number)",
                """
                SELECT po_no, line_number, COUNT(*)
                FROM {tbl}
                GROUP BY po_no, line_number
                HAVING COUNT(*) > 1
                """,
            ),
            (
                "fact_ar_allocation",
                "(payment_no, allocation_id)",
                """
                SELECT payment_no, allocation_id, COUNT(*)
                FROM {tbl}
                GROUP BY payment_no, allocation_id
                HAVING COUNT(*) > 1
                """,
            ),
        ]

        results: dict[str, dict[str, Any]] = {}
        for fact_name, grain_desc, check_sql in tests:
            tbl = self._qual("mart", fact_name)
            formatted_sql = check_sql.format(tbl=tbl)
            dups = self._fetch_all(formatted_sql)
            count_res = self._fetch_all(f"SELECT COUNT(*) AS cnt FROM {tbl}")
            cnt = int(count_res[0]["cnt"]) if count_res else 0
            results[fact_name] = {
                "passed": len(dups) == 0,
                "grain": grain_desc,
                "row_count": cnt,
                "duplicates": dups,
            }
        return results

    def verify_fact_grains(self) -> None:
        """Raises ValueError if any fact table fails grain uniqueness."""
        res = self.verify_grain_uniqueness()
        for fact_name, v in res.items():
            if not v["passed"]:
                raise ValueError(
                    f"Grain violation detected on {fact_name}: {v['duplicates']}"
                )

    def build_all(self, job_name: str = "mart_build") -> dict[str, Any]:
        """
        Builds all conformed dimensions and fact tables, verifies grains, and logs run in etl.runs.
        """
        from analytics.extract.extractor import get_session

        now = datetime.now(UTC)
        session = get_session(self.engine)

        run_record = EtlRun(
            job=job_name,
            started_at=now,
            status="running",
            rows_extracted=0,
        )
        session.add(run_record)
        session.commit()
        session.refresh(run_record)
        run_id = run_record.run_id

        try:
            dim_counts = {
                "dim_date": self.populate_dim_date(),
                "dim_source_system": self.populate_dim_source_system(),
                "dim_customer": self.build_dim_customer(scd_type=2),
                "dim_product": self.build_dim_product(),
                "dim_employee": self.build_dim_employee(),
                "dim_warehouse": self.build_dim_warehouse(),
                "dim_supplier": self.build_dim_supplier(),
            }

            fact_counts = {
                "fact_sales_line": self.build_fact_sales_line(),
                "fact_opportunity_stage": self.build_fact_opportunity_stage(),
                "fact_inventory_daily": self.build_fact_inventory_daily(),
                "fact_purchase_line": self.build_fact_purchase_line(),
                "fact_ar_allocation": self.build_fact_ar_allocation(),
            }

            grain_res = self.verify_grain_uniqueness()
            for fact_name, v in grain_res.items():
                if not v["passed"]:
                    raise ValueError(
                        f"Grain uniqueness violation on {fact_name}: {v['duplicates']}"
                    )

            total_fact_rows = sum(fact_counts.values())
            run_record.status = "success"
            run_record.rows_extracted = total_fact_rows
            run_record.finished_at = datetime.now(UTC)
            session.commit()

            return {
                "run_id": run_id,
                "status": "success",
                "dimensions": dim_counts,
                "facts": fact_counts,
                "grain_verification": grain_res,
            }
        except Exception as exc:
            run_record.status = "failed"
            run_record.error = str(exc)
            run_record.finished_at = datetime.now(UTC)
            session.commit()
            raise

    def run(self) -> dict[str, Any]:
        """Backward-compatible runner calling build_all()."""
        return self.build_all()
