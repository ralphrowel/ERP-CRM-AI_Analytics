"""
Power BI Semantic Model Exporter and Database Security Setup (Roadmap §V1.5)
Exports semantic model definitions (JSON, DAX, TMDL) and generates bi_reader role setup SQL.
"""

from pathlib import Path

from analytics.bi.dax import get_all_dax_expressions
from analytics.bi.model import SemanticModel


def generate_bi_reader_grant_sql(
    db_name: str = "erp_analytics",
    username: str = "bi_reader",
    password: str = "bi_reader_secure_pass_2026",
) -> str:
    """
    Generates PostgreSQL security script enforcing principle of least privilege:
    `bi_reader` receives read-only access exclusively to the `mart` schema,
    with explicit isolation from operational ERP schemas, raw, and staging.
    """
    return f"""-- =============================================================================
-- PostgreSQL Security Role Configuration: bi_reader (Roadmap §V1.5 & §3.2)
-- Dedicated read-only role for Power BI Desktop & Analysis Services Import Mode.
-- Enforces zero access to raw, staging, dq, and operational ERP schemas.
-- =============================================================================

-- 1. Create bi_reader user if not exists
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{username}') THEN
      CREATE ROLE {username} WITH LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
   END IF;
END
$do$;

-- 2. Grant Database Connect
GRANT CONNECT ON DATABASE {db_name} TO {username};

-- 3. Grant schema usage strictly on mart
GRANT USAGE ON SCHEMA mart TO {username};

-- 4. Grant SELECT privileges strictly on mart tables and views
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO {username};
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO {username};

-- 5. Explicitly Revoke access to sensitive operational, raw, and staging layers
REVOKE ALL ON SCHEMA raw FROM {username};
REVOKE ALL ON SCHEMA staging FROM {username};
REVOKE ALL ON SCHEMA dq FROM {username};
REVOKE ALL ON SCHEMA etl FROM {username};
REVOKE ALL ON SCHEMA public FROM {username};

-- 6. Verification query
-- SELECT table_schema, table_name, privilege_type 
-- FROM information_schema.role_table_grants 
-- WHERE grantee = '{username}';
"""


class PowerBiExporter:
    """Exports Power BI semantic assets and configuration files."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = (
            output_dir
            or Path(__file__).resolve().parent.parent.parent / "docs" / "powerbi"
        )
        self.model = SemanticModel()

    def export_all(self) -> dict[str, Path]:
        """Exports all Power BI files into output directory."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, Path] = {}

        # 1. Semantic Model JSON
        json_path = self.output_dir / "powerbi_semantic_model.json"
        json_path.write_text(self.model.to_json(), encoding="utf-8")
        results["model_json"] = json_path

        # 2. DAX Expressions File
        dax_path = self.output_dir / "powerbi_measures.dax"
        dax_path.write_text(get_all_dax_expressions(), encoding="utf-8")
        results["measures_dax"] = dax_path

        # 3. TMDL Model File
        tmdl_path = self.output_dir / "model.tmdl"
        tmdl_path.write_text(self.model.to_tmdl(), encoding="utf-8")
        results["model_tmdl"] = tmdl_path

        # 4. bi_reader Role Setup SQL
        sql_path = self.output_dir / "setup_bi_reader.sql"
        sql_path.write_text(generate_bi_reader_grant_sql(), encoding="utf-8")
        results["setup_sql"] = sql_path

        return results
