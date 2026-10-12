-- ==============================================================================
-- Database Roles and Permissions Setup (Roadmap §4.7)
-- ==============================================================================

-- 1. Create erp_owner (owns schema, used by Alembic for DDL)
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'erp_owner') THEN
      CREATE ROLE erp_owner WITH LOGIN CREATEDB PASSWORD 'erp_owner_password';
   ELSE
      ALTER ROLE erp_owner WITH CREATEDB;
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

-- 5. Create etl_reader (Roadmap §4.7 / §V1.1: SELECT only on ERP)
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'etl_reader') THEN
      CREATE ROLE etl_reader WITH LOGIN PASSWORD 'etl_reader_password';
   END IF;
END
$do$;

GRANT CONNECT ON DATABASE erp_crm TO etl_reader;
GRANT USAGE ON SCHEMA public TO etl_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO etl_reader;

ALTER DEFAULT PRIVILEGES FOR ROLE erp_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO etl_reader;

-- 6. Create analytics_owner (Roadmap §4.7 / §V1.1: owns separate analytics database)
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'analytics_owner') THEN
      CREATE ROLE analytics_owner WITH LOGIN PASSWORD 'analytics_owner_password';
   END IF;
END
$do$;

SELECT 'CREATE DATABASE erp_analytics OWNER analytics_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'erp_analytics')\gexec

GRANT ALL ON DATABASE erp_analytics TO analytics_owner;

-- 7. Ensure root and runner roles exist and root database exists
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'root') THEN
      CREATE ROLE root WITH SUPERUSER LOGIN;
   END IF;
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'runner') THEN
      CREATE ROLE runner WITH SUPERUSER LOGIN;
   END IF;
END
$do$;

SELECT 'CREATE DATABASE root OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'root')\gexec

-- 8. Connect to erp_analytics to initialize Analytics schemas and tables
\connect erp_analytics

CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dq;
CREATE SCHEMA IF NOT EXISTS mart;

ALTER SCHEMA etl OWNER TO analytics_owner;
ALTER SCHEMA raw OWNER TO analytics_owner;
ALTER SCHEMA staging OWNER TO analytics_owner;
ALTER SCHEMA dq OWNER TO analytics_owner;
ALTER SCHEMA mart OWNER TO analytics_owner;

-- Create etl.runs table compatible with both SQLAlchemy EtlRun and VisiQ Engine
CREATE TABLE IF NOT EXISTS etl.runs (
  id SERIAL,
  run_id BIGSERIAL PRIMARY KEY,
  job VARCHAR(100),
  pipeline_name VARCHAR(255) DEFAULT 'daily_pipeline',
  status VARCHAR(50) NOT NULL DEFAULT 'running',
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP,
  completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  rows_extracted INTEGER DEFAULT 0,
  records_extracted INTEGER DEFAULT 0,
  records_loaded INTEGER DEFAULT 0,
  error TEXT
);

-- Create dq.test_results table for DQ health monitoring
CREATE TABLE IF NOT EXISTS dq.test_results (
  id SERIAL PRIMARY KEY,
  test_name VARCHAR(255) NOT NULL,
  layer VARCHAR(50) NOT NULL,
  target_table VARCHAR(255) NOT NULL,
  defect_count INTEGER DEFAULT 0,
  details TEXT,
  status VARCHAR(50) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Grant schema permissions
GRANT ALL ON ALL TABLES IN SCHEMA etl, dq, raw, staging, mart TO analytics_owner;
GRANT ALL ON ALL SEQUENCES IN SCHEMA etl, dq, raw, staging, mart TO analytics_owner;
GRANT USAGE ON SCHEMA etl, dq, raw, staging, mart TO analytics_owner, erp_app, etl_reader;

\connect erp_crm


