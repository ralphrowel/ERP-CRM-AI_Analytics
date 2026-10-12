# Production Deployment & Infrastructure Guide (Milestone V1.9)

## 1. Overview & Architecture

Milestone V1.9 defines the production deployment topology for the ERP/CRM Operational Monolith. The target architecture is designed for a single Linux Virtual Machine per environment running Docker Compose, fronted by Caddy for automated TLS termination, reverse-proxying, and serving the single-page application (SPA).

```
[ Internet / Public Ingress ]
            |
            | Ports 80 (HTTP redirect) & 443 (HTTPS)
            v
+-------------------------------------------------------------+
| Caddy Reverse Proxy (docker/Caddyfile)                       |
| - Automated TLS (Let's Encrypt / ZeroSSL)                   |
| - Serves Frontend SPA (/var/www/html) with fallback routing  |
| - Enforces HSTS, CSP, and OWASP Security Headers            |
| - Proxies /api/* and /health to backend:8000                |
+-------------------------------------------------------------+
            | (Internal Docker Network: internal_net)
    +-------+--------------------+
    |                            |
    v                            v
+-----------------------+   +---------------------------------+
| FastAPI Backend       |   | Background Event Worker Daemon  |
| - 4 Uvicorn Workers   |   | - Outbox Event Dispatcher       |
| - Port 8000 (Internal)|   | - Scheduled Business Engine     |
+-----------------------+   +---------------------------------+
    |                            |
    +-------+--------------------+
            |
            v
+-------------------------------------------------------------+
| PostgreSQL 16 (postgres:16-alpine)                          |
| - Port 5432 (Internal Only - NEVER Exposed to Host Machine) |
| - Persistent Volume: postgres_data_prod                     |
+-------------------------------------------------------------+
```

---

## 2. Security & Network Invariants

### 1. Ingress Security & Unexposed Database Ports
- **PostgreSQL (5432)** is **never mapped to host ports**. It is only reachable by the `backend` and `worker` containers over the internal bridge network (`internal_net`).
- **FastAPI Backend (8000)** is also unmapped to the host machine. All external traffic must pass through Caddy.
- The host firewall exposes **only ports 80 and 443**.

### 2. Mandatory HTTP Security Headers
Every HTTP response carries strict OWASP security headers applied at both the Caddy gateway and FastAPI middleware:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` (HSTS)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; connect-src 'self';`

---

## 3. Automated Backup & Restore Verification Drills

To guarantee disaster recovery without data loss, the platform integrates automated nightly backups and restore verification testing.

### Backup Engine (`scripts/backup.py` / `scripts/backup.sh`)
- Dumps the production database using `pg_dump --clean --if-exists`.
- Timestamped output: `backups/erp_crm_backup_YYYYMMDD_HHMMSS.sql`.
- **14-day retention policy**: Backups older than 14 days are automatically pruned.

### Automated Restore Drill (`scripts/restore_test.py` / `scripts/restore_test.sh`)
- Identifies the latest backup in `backups/`.
- Provisions a temporary scratch database (`erp_crm_restore_scratch`).
- Restores the backup into the scratch database.
- Executes integrity and row-count verification across critical tables:
  `users`, `roles`, `permissions`, `customers`, `leads`, `invoices`, `outbox_events`, `notifications`.
- Drops the scratch database upon verification.
- Logs an immutable verification audit record to `backups/restore_test.log`:
  ```text
  [2026-10-12T16:53:34Z] RESTORE_TEST_SUCCESS backup=erp_crm_backup_20261012_085334.sql duration=0.15s status=SUCCESS tables_checked=8 result=PASSED
  ```

---

## 4. Continuous Deployment Pipeline (`.github/workflows/deploy.yml`)

The CD pipeline triggers automatically whenever a version tag matching `v*` (e.g., `v1.9.0`) is pushed to GitHub.

1. **`build-and-test`**:
   - Runs linting (`ruff check`, `ruff format --check`).
   - Runs backend test suite (`pytest backend/tests/unit/`).
   - Runs frontend typechecking and build (`tsc -b && vite build`).
2. **`deploy-staging`**:
   - Automatically builds production Docker images.
   - Deploys containers to the staging VM.
   - Runs database migrations with `erp_owner` credentials (`alembic upgrade head`).
   - Executes automated health check on `https://staging.erp.example.com/health`.
3. **`deploy-production`**:
   - Requires explicit human approval via GitHub Environment Protection Rules on `production`.
   - Deploys containers to the production VM.
   - Applies migrations and runs smoke tests.
