# Visiq AI Analytics Assistant Guide (Roadmap §V1.6)

Visiq is an enterprise conversational data analyst designed exclusively for the ERP/CRM learning platform. It answers complex analytical business questions over the analytical database (`mart` and `dq` schemas) using predefined, deterministic parameterized tools with **zero numeric hallucination**.

---

## 1. Core Architectural Invariants

| Principle | Architectural Rule | Enforcement Mechanism |
|---|---|---|
| **Zero Free-Form SQL** | The LLM never writes raw SQL queries. | Predefined, strictly typed tools (`get_metric`, `breakdown`, etc.) |
| **Deterministic Numbers** | Numbers are computed in SQL on `mart`; LLM only explains. | SQL aggregation engine calculates numbers before narrative synthesis |
| **Privacy by Design (RA 10173)** | PII (phone numbers, personal emails) is excluded. | `mart` dimension exclusion + regex safety filter in `VisiqAgent` |
| **Freshness & Quality Tracking** | Every response reports ETL run freshness and DQ warnings. | Metadata lookup against `etl.runs` and `dq.test_results` |
| **RBAC Authorization** | Access is restricted to authorized roles. | Gated by `analytics:use` permission (`admin`, `management`, `finance`) |
| **Audit Ledger Logging** | Every analytical interaction is permanently logged. | Synchronous write to `audit_log` (`action = 'ai_tool_call'`) |

---

## 2. Predefined Analytical Tools

Visiq routes user questions into 6 predefined, deterministic analytical tools:

```text
User Question
      │
      ▼
Visiq Intent Router
      ├── "What is our total net revenue?" ──────────────► get_metric(KPI-001)
      ├── "Compare sales 2024 vs 2025" ──────────────────► compare_periods(KPI-001, 2024, 2025)
      ├── "Who are our top 5 customers?" ────────────────► top_n(KPI-001, customer, 5)
      ├── "How does gross margin break down by region?" ──► breakdown(KPI-002, region)
      ├── "What is our data quality score?" ─────────────► dq_summary()
      └── "How is Days Sales Outstanding calculated?" ───► explain_metric(KPI-016)
```

1. **`get_metric`**: Computes single aggregate KPI value with optional date range (`start_date`, `end_date`) and dimension filters.
2. **`compare_periods`**: Compares metric values across two time periods, calculating absolute difference, percentage change, and trend direction.
3. **`top_n`**: Ranks top or bottom N dimension members by metric value, returning rank, value, and percentage share.
4. **`breakdown`**: Performs multi-dimensional decomposition of a metric across conformed dimension members (`region`, `category`, `customer`, `product`, `sales_rep`, `month`).
5. **`dq_summary`**: Retrieves data quality health scores, layer scores, and active data quality warnings.
6. **`explain_metric`**: Retrieves full technical and business documentation from the KPI dictionary.

---

## 3. Workspace Architecture & Dashboard Pinning

Visiq provides interactive workspace sessions:

1. **Dedicated Workspace Sessions (`/api/v1/visiq/sessions`)**:
   - Register curated datasets (`mart_sales`, `mart_inventory`, `mart_purchases`, `mart_all`).
   - Maintains isolated conversation history per session.
2. **Starter Business Questions (`/api/v1/visiq/sessions/{id}/suggestions`)**:
   - Inspects dataset metadata and suggests 4 starter questions on session launch.
3. **Executive KPI Dashboard & Widget Pinning (`/api/v1/visiq/sessions/{id}/widgets`)**:
   - Any metric card or chart generated during the conversation can be pinned to the session's executive grid for persistent monitoring.
4. **Interactive Plotly.js Visualizations**:
   - Geometry-driven chart selection:
     - Scalar metric -> Indicator card
     - Categorical ranking -> Horizontal bar chart
     - Multi-segment decomposition -> Donut / Bar chart
     - Time series -> Line chart with markers
     - Period comparison -> Grouped bar chart
   - Responsive dark and light mode palette synchronization.

---

## 4. REST API Reference

All endpoints are mounted under `/api/v1/visiq` and require the `analytics:use` permission:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/visiq/sessions` | Create a new analytical workspace session |
| `GET` | `/api/v1/visiq/sessions` | List active sessions for the current user |
| `GET` | `/api/v1/visiq/sessions/{session_id}` | Get session details, messages, and pinned widgets |
| `DELETE` | `/api/v1/visiq/sessions/{session_id}` | Delete a workspace session |
| `POST` | `/api/v1/visiq/sessions/{session_id}/ask` | Ask an analytical business question |
| `GET` | `/api/v1/visiq/sessions/{session_id}/suggestions` | Get 4 starter questions based on dataset schema |
| `POST` | `/api/v1/visiq/sessions/{session_id}/widgets/pin` | Pin a widget to the executive dashboard |
| `GET` | `/api/v1/visiq/sessions/{session_id}/widgets` | List pinned widgets |
| `DELETE` | `/api/v1/visiq/sessions/{session_id}/widgets/{widget_id}` | Unpin a widget |

---

## 5. Security & Read-Only Role (`visiq_reader`)

The PostgreSQL database role `visiq_reader` guarantees least-privilege analytical isolation:

```sql
-- Connect to analytics database
GRANT CONNECT ON DATABASE erp_analytics TO visiq_reader;

-- Enforce query timeout
ALTER ROLE visiq_reader SET statement_timeout = '5000ms';

-- Grant SELECT only on mart and dq schemas
GRANT USAGE ON SCHEMA mart, dq TO visiq_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mart, dq TO visiq_reader;

-- Revoke all access to operational, raw, staging, and etl layers
REVOKE ALL ON SCHEMA raw, staging, etl, public FROM visiq_reader;
```
