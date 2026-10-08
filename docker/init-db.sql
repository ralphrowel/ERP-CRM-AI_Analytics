-- ==============================================================================
-- Database Roles and Permissions Setup (Roadmap §4.7)
-- ==============================================================================

-- 1. Create erp_owner (owns schema, used by Alembic for DDL)
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'erp_owner') THEN
      CREATE ROLE erp_owner WITH LOGIN PASSWORD 'erp_owner_password';
   END IF;
END
$do$;

-- 2. Create erp_app (runs API application, DML only, no DDL)
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'erp_app') THEN
      CREATE ROLE erp_app WITH LOGIN PASSWORD 'erp_app_password';
   END IF;
END
$do$;

-- 3. Grant schema ownership and usage
GRANT ALL ON DATABASE erp_crm TO erp_owner;
ALTER SCHEMA public OWNER TO erp_owner;

GRANT USAGE ON SCHEMA public TO erp_app;

-- 4. Default privileges: any table created by erp_owner gets DML granted to erp_app
ALTER DEFAULT PRIVILEGES FOR ROLE erp_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO erp_app;

ALTER DEFAULT PRIVILEGES FOR ROLE erp_owner IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO erp_app;
