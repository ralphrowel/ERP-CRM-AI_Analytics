# SCD Type 2 Discovery Lesson: Preserving Historical Truth in Dimensional Data Warehouses

## Executive Overview
In an enterprise ERP and analytical platform, dimensions are not static; business entities change over time. Customers relocate headquarters between regions, products are re-categorized into new merchandising hierarchies, and sales representatives transfer between operating branches.

If a data warehouse updates dimensional attributes **in-place** (Slowly Changing Dimension Type 1), it rewrites history. Historical facts (such as revenue generated years ago in a specific region) retroactively shift to the customer's current region. This corrupts financial reporting, distorts regional quota compensation, and breaks historical audits.

**Slowly Changing Dimension Type 2 (SCD Type 2)** solves this flaw by creating a new dimension record with an independent surrogate key whenever tracked attributes change, preserving historical validity ranges (`valid_from`, `valid_to`, `is_current`).

---

## The Scenario

Consider an enterprise customer: **Atlas Discovery Corp** (Customer ID: `9999`, Customer No: `CUS-SCD-9999`).

1. **Calendar Year 2024**:
   - Customer is headquartered in **Luzon**.
   - An invoice `INV-SCD-2024` is issued on **June 15, 2024** for **₱100,000.00**.
2. **Calendar Year 2025**:
   - On **January 1, 2025**, Atlas Discovery Corp relocates operations to **Visayas**.
   - A subsequent invoice `INV-SCD-2025` is issued on **March 20, 2025** for **₱50,000.00**.

---

## 1. The SCD Type 1 Flaw (In-Place Overwrite)

### Mechanism
In an SCD Type 1 implementation, the customer dimension table uses the operational natural key (`customer_id`) as the primary key. When the customer moves to Visayas, an `UPDATE` statement overwrites the `region` column in place:

```sql
UPDATE dim_customer
SET region = 'Visayas'
WHERE customer_id = 9999;
```

### Table State Under Type 1

**`dim_customer` (Single Mutated Row):**
| customer_id | name | region |
|---|---|---|
| 9999 | Atlas Discovery Corp | Visayas |

**`fact_sales_line`:**
| invoice_no | doc_date | customer_id | net_revenue |
|---|---|---|---|
| INV-SCD-2024 | 2024-06-15 | 9999 | ₱100,000.00 |
| INV-SCD-2025 | 2025-03-20 | 9999 | ₱50,000.00 |

### Query: 2024 Regional Revenue Report
When the executive team or regional sales director runs the 2024 fiscal year performance report:

```sql
SELECT 
    c.region,
    SUM(f.net_revenue) AS total_net_revenue
FROM fact_sales_line f
JOIN dim_customer c ON f.customer_id = c.customer_id
WHERE f.date_key BETWEEN 20240101 AND 20241231
GROUP BY c.region;
```

### Distorted Result:
| Region | Reported Net Revenue (2024) | Expected Actual Revenue | Status |
|---|---|---|---|
| Luzon | **₱0.00** | ₱100,000.00 | **Corrupted (-₱100,000)** |
| Visayas | **₱100,000.00** | ₱0.00 | **Corrupted (+₱100,000)** |

### Impact of the Type 1 Flaw:
- **Historical Distortion**: Luzon operations generated ₱100,000 in 2024, but the report retroactively attributes that revenue to Visayas.
- **Quota & Compensation Bias**: Branch managers and regional account executives in Visayas receive credit and bonuses for sales they never produced.
- **Audit Failure**: Re-running past financial reports yields different numbers than the officially audited 2024 annual statements.

---

## 2. The SCD Type 2 Solution (Surrogate Keys & Effective Dating)

### Mechanism
In an SCD Type 2 architecture:
1. Every revision receives a distinct **surrogate primary key** (`customer_key`), separate from the operational natural key (`customer_id`).
2. Each row maintains validity timestamps (`valid_from`, `valid_to`) and an active flag (`is_current`).
3. When an attribute changes:
   - The prior row is retired by setting `valid_to = '2025-01-01'` and `is_current = 0`.
   - A new row is inserted with `customer_key = 2`, `region = 'Visayas'`, `valid_from = '2025-01-01'`, `valid_to = NULL`, and `is_current = 1`.
4. When facts are ingested, they join to `dim_customer` on `customer_id` and the transaction date:
   ```sql
   JOIN dim_customer c ON c.customer_id = i.customer_id
       AND i.issue_date >= c.valid_from
       AND (c.valid_to IS NULL OR i.issue_date < c.valid_to)
   ```
   The fact row permanently stores the specific `customer_key` that was valid at the moment the transaction occurred.

---

### Table State Under SCD Type 2

**`dim_customer`:**
| customer_key (PK) | customer_id | name | region | valid_from | valid_to | is_current |
|---|---|---|---|---|---|---|
| **101** | 9999 | Atlas Discovery Corp | Luzon | 2023-01-01 | 2025-01-01 | 0 |
| **102** | 9999 | Atlas Discovery Corp | Visayas | 2025-01-01 | NULL | 1 |

**`fact_sales_line`:**
| invoice_no | date_key | customer_key | net_revenue |
|---|---|---|---|
| INV-SCD-2024 | 20240615 | **101** | ₱100,000.00 |
| INV-SCD-2025 | 20250320 | **102** | ₱50,000.00 |

---

### Verification Queries & True Results

#### 1. 2024 Regional Revenue (Historical Accuracy Preserved)
```sql
SELECT 
    c.region,
    SUM(f.net_revenue) AS total_net_revenue
FROM fact_sales_line f
JOIN dim_customer c ON f.customer_key = c.customer_key
WHERE f.date_key BETWEEN 20240101 AND 20241231
GROUP BY c.region;
```

**Result:**
| Region | Total Net Revenue (2024) |
|---|---|
| **Luzon** | **₱100,000.00** |
| Visayas | ₱0.00 |

*Sales generated in 2024 remain securely attributed to Luzon.*

---

#### 2. 2025 Regional Revenue (Current Geography Reflected)
```sql
SELECT 
    c.region,
    SUM(f.net_revenue) AS total_net_revenue
FROM fact_sales_line f
JOIN dim_customer c ON f.customer_key = c.customer_key
WHERE f.date_key BETWEEN 20250101 AND 20251231
GROUP BY c.region;
```

**Result:**
| Region | Total Net Revenue (2025) |
|---|---|
| Luzon | ₱0.00 |
| **Visayas** | **₱50,000.00** |

*Sales generated after relocation in 2025 are accurately attributed to Visayas.*

---

#### 3. Lifetime Customer Value by Entity (Unbroken Entity Rollup)
Because both revisions share the same natural key (`customer_id = 9999`), analytical queries can seamlessly aggregate across all historical revisions:

```sql
SELECT 
    c.customer_id,
    c.name,
    SUM(f.net_revenue) AS lifetime_net_revenue
FROM fact_sales_line f
JOIN dim_customer c ON f.customer_key = c.customer_key
WHERE c.customer_id = 9999
GROUP BY c.customer_id, c.name;
```

**Result:**
| customer_id | name | lifetime_net_revenue |
|---|---|---|
| 9999 | Atlas Discovery Corp | **₱150,000.00** |

---

## Summary Comparison Matrix

| Capability | SCD Type 1 (In-Place Overwrite) | SCD Type 2 (Surrogate Key History) |
|---|---|---|
| **Storage Overhead** | Minimal (1 row per entity) | Low (1 row per revision) |
| **Historical Auditing** | Broken (past reports change) | Guaranteed (past reports immutable) |
| **Regional Sales Accuracy** | Corrupted upon move | Fully preserved per transaction date |
| **Join Complexity** | Simple natural key join | Surrogate key join (zero date filtering needed on query time) |
| **Entity Rollup** | Group by `customer_id` | Group by `customer_id` |

---

## Architectural Rules for Mart Implementation
1. **Never use operational natural keys as fact foreign keys.** Always map through surrogate keys generated at ingestion time.
2. **Surrogate keys must be immutable.** Once assigned to a historical fact row, `customer_key` never changes.
3. **Effective dating bounds must be inclusive-start, exclusive-end:** `doc_date >= valid_from AND (valid_to IS NULL OR doc_date < valid_to)`.
4. **Current record queries use `is_current = 1` or `valid_to IS NULL`.**
