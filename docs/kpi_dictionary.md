# ERP/CRM Operational KPI Dictionary

> **Authority Document**: Single source of truth for business metric definitions across operational reports, executive dashboards, and data analytics pipelines. Every report in `app/modules/reporting` and every card in the frontend UI must cite an ID from this dictionary.

---

## Metric Register

| KPI ID | Name | Domain | Primary Tables | Aggregation Grain |
|---|---|---|---|---|
| [KPI-001](#kpi-001-net-revenue) | Net Revenue | Finance / Sales | `invoices`, `credit_notes` | Date / Month / Period |
| [KPI-002](#kpi-002-gross-margin) | Gross Margin | Finance / Sales | `invoices`, `shipments`, `products` | Month / Period |
| [KPI-003](#kpi-003-gross-margin-pct) | Gross Margin % | Finance / Sales | KPI-002 / KPI-001 | Period |
| [KPI-004](#kpi-004-confirmed-orders) | Confirmed Orders | Sales | `sales_orders`, `status_history` | Day / Month |
| [KPI-005](#kpi-005-ar-outstanding) | AR Outstanding | Finance | `invoices` | Point in time (As of date) |
| [KPI-006](#kpi-006-ar-aging) | AR Aging Buckets | Finance | `invoices` | Due date buckets |
| [KPI-007](#kpi-007-weighted-pipeline) | Weighted Pipeline | CRM | `opportunities` | Current open snapshot |
| [KPI-008](#kpi-008-win-rate) | Win Rate | CRM | `opportunities` | Closed cohort period |
| [KPI-009](#kpi-009-lead-conversion-rate) | Lead Conversion Rate | CRM | `leads` | Created cohort period |
| [KPI-010](#kpi-010-avg-sales-cycle) | Average Sales Cycle | CRM | `opportunities` | Won cohort in period |
| [KPI-011](#kpi-011-active-customers) | Active Customers | Sales / CRM | `invoices` | Trailing 12 months |
| [KPI-012](#kpi-012-new-customers) | New Customers | Sales / CRM | `invoices` | Invoicing cohort |
| [KPI-013](#kpi-013-inventory-value) | Inventory Value | Inventory | `inventory_balances`, `products` | Point in time |
| [KPI-014](#kpi-014-inventory-turnover) | Inventory Turnover | Inventory | `inventory_transactions`, `balances` | Trailing 12 months |
| [KPI-015](#kpi-015-low-stock-items) | Low-Stock Items | Inventory | `inventory_balances`, `products` | Current threshold alert |
| [KPI-016](#kpi-016-purchase-spend) | Purchase Spend | Purchasing | `supplier_invoices` | Month / Period |
| [KPI-017](#kpi-017-supplier-on-time-rate) | Supplier On-Time Rate | Purchasing | `purchase_orders`, `goods_receipts` | Completed orders |
| [KPI-018](#kpi-018-days-sales-outstanding) | Days Sales Outstanding (DSO) | Finance | KPI-005, KPI-001 | Trailing 90 days |

---

## Detailed KPI Specifications

### KPI-001: Net Revenue
- **Domain**: Finance / Commercial Sales
- **Definition**: The net invoiced revenue recognized on an accrual basis within the selected period, excluding VAT (value-added tax) and net of issued credit notes.
- **Formula**:
  $$\text{Net Revenue} = \sum \text{Invoice Subtotal} - \sum \text{Credit Note Subtotal}$$
- **Filters**:
  - Invoices: `status IN ('issued', 'partially_paid', 'paid')`, grouped by `issue_date` in Asia/Manila.
  - Credit Notes: `status = 'issued'`, grouped by `issue_date` in Asia/Manila.
  - Cancelled, voided, or draft documents are strictly excluded.
- **Data Source**: `invoices(subtotal, status, issue_date)` and `credit_notes(subtotal, status, issue_date)`.

---

### KPI-002: Gross Margin
- **Domain**: Finance / Operations
- **Definition**: The total peso profit remaining from Net Revenue after subtracting the Cost of Goods Sold (COGS) incurred to fulfill those customer commitments.
- **Formula**:
  $$\text{Gross Margin} = \text{Net Revenue} - \text{COGS}$$
- **Filters**:
  - COGS calculated from posted shipments with `status IN ('shipped', 'delivered')` multiplied by snapshot unit cost, or standard item line cost basis.

---

### KPI-003: Gross Margin %
- **Domain**: Finance / Executive Management
- **Definition**: The percentage of revenue that exceeds COGS.
- **Formula**:
  $$\text{Gross Margin \%} = \frac{\text{KPI-002 (Gross Margin)}}{\text{KPI-001 (Net Revenue)}} \times 100$$

---

### KPI-004: Confirmed Orders
- **Domain**: Commercial Sales
- **Definition**: Count of sales orders officially confirmed within the target period.
- **Formula**:
  $$\text{Confirmed Orders} = \text{COUNT}(\text{sales\_orders where status} \in ('confirmed', 'processing', 'completed'))$$
- **Filters**: Counted based on transition timestamp to `confirmed` in `status_history` (or `order_date`).

---

### KPI-005: AR Outstanding
- **Domain**: Accounts Receivable
- **Definition**: Total unpaid balance currently owed by customers on issued and partially paid sales invoices as of the calculation date.
- **Formula**:
  $$\text{AR Outstanding} = \sum \text{balance\_due}$$
- **Filters**:
  - `status IN ('issued', 'partially_paid')`.
  - Excludes paid, void, and draft invoices.

---

### KPI-006: AR Aging
- **Domain**: Accounts Receivable / Credit Control
- **Definition**: Segmentation of total outstanding accounts receivable based on days elapsed past the invoice `due_date`.
- **Buckets**:
  1. **Current**: `due_date >= CURRENT_DATE` (not yet overdue)
  2. **1–30 Days Overdue**: `1 <= (CURRENT_DATE - due_date) <= 30`
  3. **31–60 Days Overdue**: `31 <= (CURRENT_DATE - due_date) <= 60`
  4. **61–90 Days Overdue**: `61 <= (CURRENT_DATE - due_date) <= 90`
  5. **90+ Days Overdue**: `(CURRENT_DATE - due_date) > 90`
- **Data Source**: `invoices(balance_due, due_date, status, customer_id)`.

---

### KPI-007: Weighted Pipeline
- **Domain**: CRM / Sales Forecasting
- **Definition**: Total expected value of open opportunities weighted by their respective probability of winning.
- **Formula**:
  $$\text{Weighted Pipeline} = \sum (\text{estimated\_amount} \times \text{probability})$$
- **Filters**: `stage NOT IN ('won', 'lost')` and `is_active = true`.

---

### KPI-008: Win Rate
- **Domain**: CRM / Sales Performance
- **Definition**: Ratio of deals won compared to all deals closed within the specified date range.
- **Formula**:
  $$\text{Win Rate} = \frac{\text{COUNT}(\text{opportunities with stage = 'won'})}{\text{COUNT}(\text{opportunities with stage} \in ('won', 'lost'))} \times 100$$
- **Filters**: Evaluated on opportunities whose stage transition to won/lost falls within the period.

---

### KPI-009: Lead Conversion Rate
- **Domain**: CRM / Marketing & Inbound
- **Definition**: Percentage of leads converted into qualified opportunities or customers out of total leads created in the same cohort.
- **Formula**:
  $$\text{Conversion Rate} = \frac{\text{COUNT}(\text{leads with status = 'converted'})}{\text{COUNT}(\text{leads created in period})} \times 100$$

---

### KPI-010: Average Sales Cycle
- **Domain**: CRM / Sales Velocity
- **Definition**: Average calendar days elapsed from initial opportunity creation to the date the deal is marked as Won.
- **Formula**:
  $$\text{Avg Sales Cycle} = \text{AVG}(\text{closed\_at} - \text{created\_at}) \quad \text{for stage = 'won'}$$

---

### KPI-011: Active Customers
- **Domain**: Commercial Sales / Customer Success
- **Definition**: Distinct count of unique customers who have had at least one issued sales invoice in the trailing 12 months.
- **Formula**:
  $$\text{Active Customers} = \text{COUNT(DISTINCT customer\_id)} \quad \text{where invoice issue\_date} \ge \text{now} - 365\text{ days}$$

---

### KPI-012: New Customers
- **Domain**: Commercial Sales
- **Definition**: Count of customers whose very first sales invoice issue date falls within the selected period.

---

### KPI-013: Inventory Value
- **Domain**: Inventory & Supply Chain
- **Definition**: Total capital tied up in stock across all warehouses, valued at weighted-average unit cost (WAC).
- **Formula**:
  $$\text{Inventory Value} = \sum (\text{qty\_on\_hand} \times \text{avg\_unit\_cost})$$
- **Filters**: Grouped by warehouse and product category.

---

### KPI-015: Low-Stock Items
- **Domain**: Inventory & Logistics
- **Definition**: Count and list of products where total available quantity across warehouses has fallen below the defined reorder threshold.
- **Condition**:
  $$\text{Available Qty} (\text{qty\_on\_hand} - \text{qty\_reserved}) < \text{reorder\_point}$$
- **Filters**: Stock-type active products where `reorder_point > 0`.

---

### KPI-016: Purchase Spend
- **Domain**: Procurement & Accounts Payable
- **Definition**: Total procurement obligations approved on supplier invoices/bills within the period (VAT-exclusive).
- **Formula**:
  $$\text{Purchase Spend} = \sum \text{supplier\_invoices.subtotal} \quad \text{where status} \in ('approved', 'partially_paid', 'paid')$$

---

### KPI-017: Supplier On-Time Rate
- **Domain**: Procurement & Vendor Management
- **Definition**: Percentage of purchase order lines delivered on or before the promised delivery date.
- **Formula**:
  $$\text{On-Time Delivery \%} = \frac{\text{Receipt Lines with receipt\_date} \le \text{po\_line.expected\_date}}{\text{Total Completed PO Lines}} \times 100$$

---

### KPI-018: Days Sales Outstanding (DSO)
- **Domain**: Finance / Cash Flow
- **Definition**: Average number of days taken to collect payment on sales.
- **Formula**:
  $$\text{DSO} = \frac{\text{KPI-005 (AR Outstanding)}}{\text{KPI-001 (Net Revenue Trailing 90 Days)} / 90}$$

---

## Known OLTP Query Limitations (Phase 1 Baseline)

1. **Slow Aggregations on Large History**: Calculating trailing 12-month metrics across transactional OLTP tables competes with OLTP write locks (`SELECT ... FOR UPDATE`).
2. **Dimension Mutation**: If a customer changes departments or categories, historical OLTP queries group past revenue under their *current* attributes (lack of Slowly Changing Dimensions).
3. **Complex Outer Joins**: Blending invoices and credit notes requires `FULL OUTER JOIN`, which increases CPU and memory consumption without pre-aggregated mart tables.

*These explicit limitations serve as the foundational motivation for Phase 2: Analytics Data Platform (Extraction, Transformation, and Data Marts).*
