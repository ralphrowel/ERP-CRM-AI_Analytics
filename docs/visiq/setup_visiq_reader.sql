-- =============================================================================
-- PostgreSQL Security Role Configuration: visiq_reader (Roadmap §V1.6 & §3.2)
-- Dedicated read-only role for Visiq AI Analytics Assistant.
-- Enforces zero access to operational ERP, raw, staging, and etl schemas.
-- Permitted schemas: mart and dq only.
-- Enforces 5000ms statement_timeout.
-- =============================================================================

-- 1. Create visiq_reader user if not exists
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'visiq_reader') THEN
      CREATE ROLE visiq_reader WITH LOGIN PASSWORD 'visiq_reader_secure_pass_2026' NOSUPERUSER NOCREATEDB NOCREATEROLE;
   END IF;
END
$do$;

-- 2. Grant Database Connect
GRANT CONNECT ON DATABASE erp_analytics TO visiq_reader;

-- 3. Configure statement timeout for security and query governance
ALTER ROLE visiq_reader SET statement_timeout = '5000ms';

-- 4. Grant schema usage strictly on mart and dq
GRANT USAGE ON SCHEMA mart TO visiq_reader;
GRANT USAGE ON SCHEMA dq TO visiq_reader;

-- 5. Grant SELECT privileges strictly on mart and dq tables and views
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO visiq_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA dq TO visiq_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO visiq_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq GRANT SELECT ON TABLES TO visiq_reader;

-- 6. Explicitly Revoke access to raw, staging, etl, and public layers
REVOKE ALL ON SCHEMA raw FROM visiq_reader;
REVOKE ALL ON SCHEMA staging FROM visiq_reader;
REVOKE ALL ON SCHEMA etl FROM visiq_reader;
REVOKE ALL ON SCHEMA public FROM visiq_reader;

-- 7. Verification query
-- SELECT table_schema, table_name, privilege_type 
-- FROM information_schema.role_table_grants 
-- WHERE grantee = 'visiq_reader';
