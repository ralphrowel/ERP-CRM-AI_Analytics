"""
Legacy Dirty-Data Generator (Roadmap §V1.0 Path B)
Generates realistic legacy exports (legacy_customers.csv, legacy_sales_2023_2025.csv)
with controlled, measured defects and outputs a reproducible defect manifest JSON.
"""

import csv
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PH_CITIES = [
    ("Manila", "Metro Manila"),
    ("Quezon City", "Metro Manila"),
    ("Makati", "Metro Manila"),
    ("Taguig", "Metro Manila"),
    ("Pasig", "Metro Manila"),
    ("Mandaluyong", "Metro Manila"),
    ("Cebu City", "Cebu"),
    ("Davao City", "Davao del Sur"),
    ("Iloilo City", "Iloilo"),
    ("Angeles", "Pampanga"),
    ("Baguio", "Benguet"),
    ("Calamba", "Laguna"),
]

CITY_VARIANTS: dict[str, list[str]] = {
    "Quezon City": ["QC", "Q.C.", "Quezon City ", "QUEZON CITY", "Q. City"],
    "Manila": [" Manila ", "MANILA", "City of Manila", "Mnl"],
    "Makati": ["makati", "Makati City", "MAKATI "],
    "Taguig": ["BGC, Taguig", "Taguig City", "TAGUIG"],
    "Pasig": ["Pasig City", "PASIG", " Ortigas, Pasig"],
    "Cebu City": ["Cebu", "CEBU CITY", "Cebu "],
    "Davao City": ["Davao", "DAVAO CITY"],
}

COMPANY_BASE_NAMES = [
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
    "BDO Capital Partners",
    "Metrobank Logistics",
    "Puregold Price Club",
    "Jollibee Food Supplies",
]

NAME_VARIANTS: dict[str, str] = {
    "Ayala Logistics Corp.": "Ayala Logistics Corporation",
    "San Miguel Packaging": "San Miguel Packaging, Inc.",
    "JG Summit Holdings": "J.G. Summit Holdings Co.",
    "Megawide Engineering": "MEGAWIDE ENG.",
    "Aboitiz Power Systems": "Aboitiz Power",
    "DMCI Holdings PH": "D.M.C.I. Holdings",
    "Robinsons Retail Hub": "Robinsons Retail",
    "Puregold Price Club": "Puregold Price Club Inc.",
}

STANDARD_SKUS = [
    "SKU-IND-BOLT-01",
    "SKU-IND-STEEL-10",
    "SKU-OFF-CHAIR-05",
    "SKU-ELEC-CABLE-02",
    "SKU-PKG-BOX-50",
    "SKU-SERV-MAINT-HR",
    "SKU-IND-MOTOR-3P",
    "SKU-CHEM-SOLV-20L",
]


class LegacyDataGenerator:
    def __init__(self, seed: int = 7, out_dir: Path | None = None) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.out_dir = out_dir or Path("data/legacy")
        self.defects: list[dict[str, Any]] = []

    def run(self, customer_count: int = 200, sales_count: int = 1500) -> dict[str, Any]:
        """
        Generates legacy customer and sales records with measured defects.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.defects.clear()

        # 1. Generate Legacy Customers
        customers = self._generate_customers(customer_count)

        # 2. Generate Legacy Sales (2023 - 2025)
        sales = self._generate_sales(customers, sales_count)

        # 3. Write CSVs
        cust_file = self.out_dir / "legacy_customers.csv"
        sales_file = self.out_dir / "legacy_sales_2023_2025.csv"

        with open(cust_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "legacy_customer_id",
                    "customer_name",
                    "contact_email",
                    "phone_number",
                    "tax_id",
                    "city",
                    "province",
                    "credit_terms",
                    "credit_limit",
                ],
            )
            writer.writeheader()
            writer.writerows(customers)

        with open(sales_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "invoice_no",
                    "order_date",
                    "legacy_customer_id",
                    "customer_name",
                    "sku",
                    "item_description",
                    "quantity",
                    "unit_price",
                    "total_amount",
                    "payment_status",
                ],
            )
            writer.writeheader()
            writer.writerows(sales)

        # 4. Write Defect Manifest
        counts_by_type: dict[str, int] = {}
        for d in self.defects:
            t = d["defect_type"]
            counts_by_type[t] = counts_by_type.get(t, 0) + 1

        manifest = {
            "generator_seed": self.seed,
            "generated_at": datetime.now(UTC).isoformat(),
            "customer_records": len(customers),
            "sales_records": len(sales),
            "total_defects": len(self.defects),
            "defects_by_type": counts_by_type,
            "defects": self.defects,
        }

        manifest_file = self.out_dir / "defect_manifest.json"
        with open(manifest_file, mode="w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return {
            "customers_path": str(cust_file),
            "sales_path": str(sales_file),
            "manifest_path": str(manifest_file),
            "total_defects": len(self.defects),
            "defects_by_type": counts_by_type,
        }

    def _generate_customers(self, count: int) -> list[dict[str, Any]]:
        records = []
        for i in range(1, count + 1):
            row_idx = i + 1  # 1-indexed header + row
            base_name = self.rng.choice(COMPANY_BASE_NAMES)
            cust_name = base_name
            city_tuple = self.rng.choice(PH_CITIES)
            city = city_tuple[0]
            province = city_tuple[1]
            raw_email = f"info@{base_name.split()[0].lower()}.ph"
            email = raw_email
            raw_phone = f"0917{self.rng.randint(1000000, 9999999)}"
            phone = raw_phone
            clean_limit = f"{self.rng.randint(5, 50) * 10000}.00"
            credit_limit = clean_limit

            # Defect Injection: Duplicate Customer Name Variant
            if self.rng.random() < 0.15 and base_name in NAME_VARIANTS:
                variant_name = NAME_VARIANTS[base_name]
                cust_name = variant_name
                self.defects.append(
                    {
                        "file": "legacy_customers.csv",
                        "row": row_idx,
                        "column": "customer_name",
                        "defect_type": "duplicate_variant",
                        "injected_value": variant_name,
                        "canonical_entity": base_name,
                    }
                )

            # Defect Injection: Whitespace and Casing
            if self.rng.random() < 0.18:
                casing_choice = self.rng.choice([f"  {city}  ", city.upper(), city.lower()])
                self.defects.append(
                    {
                        "file": "legacy_customers.csv",
                        "row": row_idx,
                        "column": "city",
                        "defect_type": "whitespace_casing",
                        "injected_value": casing_choice,
                        "clean_value": city,
                    }
                )
                city = casing_choice

            # Defect Injection: City Spelling Variant
            elif self.rng.random() < 0.20 and city in CITY_VARIANTS:
                variant_city = self.rng.choice(CITY_VARIANTS[city])
                self.defects.append(
                    {
                        "file": "legacy_customers.csv",
                        "row": row_idx,
                        "column": "city",
                        "defect_type": "spelling_variant",
                        "injected_value": variant_city,
                        "clean_value": city,
                    }
                )
                city = variant_city

            # Defect Injection: Non-standard Phone Formats
            if self.rng.random() < 0.25:
                formatted_phone = self.rng.choice(
                    [
                        f"+63 917 {phone[4:7]} {phone[7:]}",
                        f"(02) 8{phone[4:7]}-{phone[7:11]}",
                        f"+63-917-{phone[4:7]}-{phone[7:]}",
                        f"{phone[:4]} {phone[4:7]} {phone[7:]}",
                    ]
                )
                self.defects.append(
                    {
                        "file": "legacy_customers.csv",
                        "row": row_idx,
                        "column": "phone_number",
                        "defect_type": "nonstandard_phone",
                        "injected_value": formatted_phone,
                        "clean_value": raw_phone,
                    }
                )
                phone = formatted_phone

            # Defect Injection: Missing Email
            if self.rng.random() < 0.12:
                missing_val = self.rng.choice(["", "N/A", "none@domain"])
                self.defects.append(
                    {
                        "file": "legacy_customers.csv",
                        "row": row_idx,
                        "column": "contact_email",
                        "defect_type": "missing_email",
                        "injected_value": missing_val,
                        "clean_value": raw_email,
                    }
                )
                email = missing_val

            # Defect Injection: Number as text with ₱ and commas
            if self.rng.random() < 0.20:
                limit_float = float(clean_limit)
                dirty_limit = self.rng.choice(
                    [
                        f"₱ {limit_float:,.2f}",
                        f"PHP {limit_float:,.2f}",
                        f"{limit_float:,.2f}",
                    ]
                )
                self.defects.append(
                    {
                        "file": "legacy_customers.csv",
                        "row": row_idx,
                        "column": "credit_limit",
                        "defect_type": "currency_formatting",
                        "injected_value": dirty_limit,
                        "clean_value": clean_limit,
                    }
                )
                credit_limit = dirty_limit

            records.append(
                {
                    "legacy_customer_id": f"LEG-CUS-{i:04d}",
                    "customer_name": cust_name,
                    "contact_email": email,
                    "phone_number": phone,
                    "tax_id": f"{self.rng.randint(100, 999)}-{self.rng.randint(100, 999)}-{self.rng.randint(100, 999)}-000",
                    "city": city,
                    "province": province,
                    "credit_terms": f"{self.rng.choice([0, 15, 30, 60])} days",
                    "credit_limit": credit_limit,
                }
            )
        return records

    def _generate_sales(
        self, customers: list[dict[str, Any]], count: int
    ) -> list[dict[str, Any]]:
        records = []
        base_date = datetime(2023, 1, 15, 10, 0, 0, tzinfo=UTC)

        for i in range(1, count + 1):
            row_idx = i + 1
            cust = self.rng.choice(customers)
            # Date progression over 24 months (730 days)
            day_offset = self.rng.randint(0, 720)
            order_dt = base_date + timedelta(days=day_offset)
            iso_date = order_dt.strftime("%Y-%m-%d")
            order_date_str = iso_date

            sku = self.rng.choice(STANDARD_SKUS)
            qty = self.rng.randint(1, 50)
            unit_price = round(self.rng.uniform(150.0, 4500.0), 2)
            total_amt = round(qty * unit_price, 2)
            amt_str = f"{total_amt:.2f}"

            # Defect: Ambiguous or nonstandard Date formatting
            if self.rng.random() < 0.15:
                dirty_date = self.rng.choice(
                    [
                        order_dt.strftime("%m/%d/%Y"),
                        order_dt.strftime("%d/%m/%Y"),
                        order_dt.strftime("%Y.%m.%d"),
                        "2024-02-30",  # Invalid date
                    ]
                )
                self.defects.append(
                    {
                        "file": "legacy_sales_2023_2025.csv",
                        "row": row_idx,
                        "column": "order_date",
                        "defect_type": "ambiguous_date",
                        "injected_value": dirty_date,
                        "clean_value": iso_date,
                    }
                )
                order_date_str = dirty_date

            # Defect: Orphan Product Code
            if self.rng.random() < 0.08:
                orphan_sku = self.rng.choice(["OLD-SYS-999", "OBSOLETE-ITEM", "UNLISTED-PROD"])
                self.defects.append(
                    {
                        "file": "legacy_sales_2023_2025.csv",
                        "row": row_idx,
                        "column": "sku",
                        "defect_type": "orphan_product",
                        "injected_value": orphan_sku,
                        "clean_value": None,
                    }
                )
                sku = orphan_sku

            # Defect: Negative Quantity
            if self.rng.random() < 0.07:
                neg_qty = -abs(qty)
                self.defects.append(
                    {
                        "file": "legacy_sales_2023_2025.csv",
                        "row": row_idx,
                        "column": "quantity",
                        "defect_type": "negative_quantity",
                        "injected_value": neg_qty,
                        "clean_value": qty,
                    }
                )
                qty = neg_qty

            # Defect: Currency formatting on Amount
            if self.rng.random() < 0.18:
                dirty_amt = self.rng.choice(
                    [
                        f"₱ {total_amt:,.2f}",
                        f"PHP {total_amt:,.2f}",
                        f"{total_amt:,.2f}",
                    ]
                )
                self.defects.append(
                    {
                        "file": "legacy_sales_2023_2025.csv",
                        "row": row_idx,
                        "column": "total_amount",
                        "defect_type": "currency_formatting",
                        "injected_value": dirty_amt,
                        "clean_value": amt_str,
                    }
                )
                amt_str = dirty_amt

            records.append(
                {
                    "invoice_no": f"LEG-INV-{2023 + (day_offset // 365)}-{i:05d}",
                    "order_date": order_date_str,
                    "legacy_customer_id": cust["legacy_customer_id"],
                    "customer_name": cust["customer_name"],
                    "sku": sku,
                    "item_description": f"Standard Legacy Product ({sku})",
                    "quantity": qty,
                    "unit_price": f"{unit_price:.2f}",
                    "total_amount": amt_str,
                    "payment_status": self.rng.choice(["PAID", "SETTLED", "PENDING", "OVERDUE"]),
                }
            )

        return records
