-- =============================================================================
-- PostgreSQL Security Role Configuration: bi_reader (Roadmap §V1.5 & §3.2)
-- Dedicated read-only role for Power BI Desktop & Analysis Services Import Mode.
-- Enforces zero access to raw, staging, dq, and operational ERP schemas.
-- =============================================================================

-- 1. Create bi_reader user if not exists
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bi_reader') THEN
      CREATE ROLE bi_reader WITH LOGIN PASSWORD 'bi_reader_secure_pass_2026' NOSUPERUSER NOCREATEDB NOCREATEROLE;
   END IF;
END
$do$;

-- 2. Grant Database Connect
GRANT CONNECT ON DATABASE erp_analytics TO bi_reader;

-- 3. Grant schema usage strictly on mart
GRANT USAGE ON SCHEMA mart TO bi_reader;

-- 4. Grant SELECT privileges strictly on mart tables and views
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO bi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO bi_reader;

-- 5. Explicitly Revoke access to sensitive operational, raw, and staging layers
REVOKE ALL ON SCHEMA raw FROM bi_reader;
REVOKE ALL ON SCHEMA staging FROM bi_reader;
REVOKE ALL ON SCHEMA dq FROM bi_reader;
REVOKE ALL ON SCHEMA etl FROM bi_reader;
REVOKE ALL ON SCHEMA public FROM bi_reader;

-- 6. Verification query
-- SELECT table_schema, table_name, privilege_type 
-- FROM information_schema.role_table_grants 
-- WHERE grantee = 'bi_reader';
