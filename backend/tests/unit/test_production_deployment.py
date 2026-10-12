"""Unit Tests for Production Deployment & Infrastructure (Roadmap §V1.9)

Validates Milestone V1.9 Exit Criteria:
1. Tagging a release deploys to staging automatically and to production with one approval.
2. A restore test from last night's backup succeeds and is logged.
3. The app is reachable only over HTTPS; DB ports are not publicly exposed.
"""

import os
import time
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from scripts.backup import prune_old_backups, run_backup
from scripts.restore_test import CORE_TABLES_TO_VERIFY, run_restore_test

from app.main import app

# =============================================================================
# Exit Criterion 1: CD Pipeline Configuration & Approval Gates
# =============================================================================


def test_cd_pipeline_configuration_staging_and_production_approval():
    """Validates that .github/workflows/deploy.yml specifies automated staging and gated production."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    deploy_wf = repo_root / ".github" / "workflows" / "deploy.yml"

    assert deploy_wf.exists(), "deploy.yml must exist in .github/workflows"

    with open(deploy_wf, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 1. Triggered on release tags (v*)
    on_trigger = config.get("on") or config.get(True)
    assert "push" in on_trigger, "Workflow must trigger on git push"
    tags = on_trigger["push"].get("tags", [])
    assert any("v*" in tag for tag in tags), "Workflow must trigger on 'v*' tags"

    jobs = config.get("jobs", {})
    assert "build-and-test" in jobs, "Must have build-and-test job"
    assert "deploy-staging" in jobs, "Must have deploy-staging job"
    assert "deploy-production" in jobs, "Must have deploy-production job"

    # 2. Staging depends on build-and-test, deploys automatically
    staging_job = jobs["deploy-staging"]
    assert staging_job.get("needs") == "build-and-test"
    staging_env = staging_job.get("environment", {})
    assert staging_env.get("name") == "staging"

    # 3. Production depends on deploy-staging and is protected with 'production' environment approval
    prod_job = jobs["deploy-production"]
    assert prod_job.get("needs") == "deploy-staging"
    prod_env = prod_job.get("environment", {})
    assert prod_env.get("name") == "production", (
        "Production deployment must use 'production' environment"
    )


# =============================================================================
# Exit Criterion 2: Automated Backup and Restore Drill with Logging
# =============================================================================


def test_automated_backup_and_restore_drill_succeeds_and_is_logged(tmp_path: Path):
    """
    Validates that:
    1. A database backup is created with timestamped naming.
    2. Retention pruning removes obsolete backups older than 14 days.
    3. A restore verification test succeeds, checks core tables, and appends to restore_test.log.
    """
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate test backup
    backup_file = run_backup(backup_dir=backup_dir, retention_days=14)
    assert backup_file.exists()
    assert backup_file.name.startswith("erp_crm_backup_")
    assert backup_file.name.endswith(".sql")

    # 2. Retention test: create an old file, set mtime to 30 days ago, and verify prune
    old_file = backup_dir / "erp_crm_backup_20200101_000000.sql"
    old_file.write_text("-- old backup", encoding="utf-8")
    thirty_days_ago = time.time() - (30 * 86400)
    os.utime(old_file, (thirty_days_ago, thirty_days_ago))

    pruned = prune_old_backups(backup_dir=backup_dir, retention_days=14)
    assert pruned >= 1
    assert not old_file.exists()

    # 3. Run restore verification drill
    result = run_restore_test(
        backup_file=backup_file,
        backup_dir=backup_dir,
        scratch_db_name="test_scratch_db",
    )
    assert result["success"] is True
    assert result["backup_name"] == backup_file.name
    assert "verified_tables" in result
    for tbl in CORE_TABLES_TO_VERIFY:
        assert tbl in result["verified_tables"]

    # 4. Assert structured log was written to restore_test.log
    log_file = backup_dir / "restore_test.log"
    assert log_file.exists()
    log_content = log_file.read_text(encoding="utf-8")
    assert "RESTORE_TEST_SUCCESS" in log_content
    assert backup_file.name in log_content
    assert "status=SUCCESS" in log_content
    assert "result=PASSED" in log_content


# =============================================================================
# Exit Criterion 3: HTTPS Only & No DB Ports Exposed on Host
# =============================================================================


def test_production_compose_does_not_expose_database_ports():
    """
    Validates that in docker-compose.prod.yml:
    - Postgres database port (5432) is NOT mapped/published to the host machine.
    - Backend application port (8000) is NOT mapped/published to the host machine.
    - Only Caddy (ports 80 and 443) is published to the public network.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    compose_path = repo_root / "docker-compose.prod.yml"

    assert compose_path.exists(), "docker-compose.prod.yml must exist"

    with open(compose_path, encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    assert "caddy" in services, "Caddy web service must be configured"
    assert "postgres" in services, "Postgres service must be configured"
    assert "backend" in services, "Backend service must be configured"
    assert "worker" in services, "Worker service must be configured"

    # PostgreSQL security check: No host port mapping!
    pg_service = services["postgres"]
    assert "ports" not in pg_service or not pg_service["ports"], (
        "Postgres service in docker-compose.prod.yml MUST NOT have 'ports' published to host"
    )

    # Backend security check: No host port mapping!
    be_service = services["backend"]
    assert "ports" not in be_service or not be_service["ports"], (
        "Backend service in docker-compose.prod.yml MUST NOT have 'ports' published to host"
    )

    # Worker security check: No host port mapping!
    worker_service = services["worker"]
    assert "ports" not in worker_service or not worker_service["ports"], (
        "Worker service in docker-compose.prod.yml MUST NOT have 'ports' published to host"
    )

    # Caddy ingress check: Only ports 80/443 exposed
    caddy_ports = services["caddy"].get("ports", [])
    assert "80:80" in caddy_ports
    assert "443:443" in caddy_ports


def test_caddyfile_enforces_tls_reverse_proxy_and_security_headers():
    """Validates that docker/Caddyfile configures TLS, reverse proxy, and headers."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    caddyfile = repo_root / "docker" / "Caddyfile"

    assert caddyfile.exists(), "Caddyfile must exist in docker/"
    content = caddyfile.read_text(encoding="utf-8")

    # TLS directive
    assert "tls" in content

    # Reverse proxy to backend for /api/*
    assert "reverse_proxy backend:8000" in content

    # Security headers
    assert "Strict-Transport-Security" in content
    assert "X-Content-Type-Options" in content
    assert "X-Frame-Options" in content
    assert "Content-Security-Policy" in content


def test_api_security_headers_and_observability_endpoints():
    """Validates FastAPI responses include OWASP security headers, /health, and /ready."""
    from unittest.mock import MagicMock, patch

    client = TestClient(app)

    # 1. Health liveness probe
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    # 2. Readiness probe with connected DB
    with patch("app.main.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        res_ready = client.get("/ready")
        assert res_ready.status_code == 200
        assert res_ready.json()["status"] == "ready"

    # 3. Readiness probe failure when DB disconnected
    with patch("app.main.SessionLocal", side_effect=Exception("Database offline")):
        res_unhealthy = client.get("/ready")
        assert res_unhealthy.status_code == 503
        assert res_unhealthy.json()["status"] == "unhealthy"

    # 4. Security headers on all HTTP responses
    headers = res_health.headers
    assert (
        headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains; preload"
    )
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in headers
    assert "Content-Security-Policy" in headers
