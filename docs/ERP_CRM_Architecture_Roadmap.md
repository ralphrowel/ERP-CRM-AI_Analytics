# ERP/CRM Learning Platform
## Versioned Architecture, Data Model & Implementation Roadmap

> **Purpose:** Build a simplified but architecturally realistic ERP/CRM platform as a learning project. Each version introduces one major business or engineering concept while keeping previous versions functional.

---

# 1. Final Target Architecture

```text
                    ┌──────────────────────────┐
                    │       BUSINESS USERS     │
                    │ Sales / Ops / Management │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │        ERP / CRM         │
                    │                          │
                    │ CRM │ Sales │ Inventory  │
                    │ Purchasing │ Finance     │
                    │ Employees │ Workflows    │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │       FastAPI API        │
                    │ Auth / RBAC / Validation │
                    │ Business Logic           │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │       PostgreSQL         │
                    │   Operational Database   │
                    └────────────┬─────────────┘
                                 │
                              ETL / ELT
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │     DATA QUALITY         │
                    │ Profile / Validate       │
                    │ Clean / Score / Lineage  │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │ ANALYTICS / DATA MART    │
                    │ Facts / Dimensions / KPI │
                    └────────────┬─────────────┘
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
              ┌─────────────┐         ┌─────────────┐
              │  Power BI   │         │    Visiq    │
              │ Dashboards  │         │ AI Analyst  │
              └─────────────┘         └─────────────┘
```

---

# 2. Core Architecture Principles

1. **Operational system first**  
   The ERP/CRM generates realistic business transactions.

2. **PostgreSQL is the operational source of truth**  
   The ERP/CRM owns transactional data.

3. **Separate operational and analytical workloads**  
   ERP answers "What is happening?"  
   Analytics answers "What happened, why, and what patterns exist?"

4. **Preserve history**  
   Important state changes should be represented through status/history/audit records rather than silently overwriting history.

5. **Deterministic business logic over AI**  
   AI may explain, summarize, classify, or assist, but should not be the authority for financial totals, inventory quantities, payment status, or core data-quality calculations.

---

# 3. Initial Technology Stack

## Frontend

- React
- Vite
- Tailwind CSS

Responsibilities:

- dashboards
- forms
- tables
- CRM workspace
- ERP workspace
- reporting interfaces

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy

Responsibilities:

- REST API
- authentication
- authorization
- validation
- business logic
- database access
- integrations

## Database

- PostgreSQL

Responsibilities:

- operational data
- relationships
- constraints
- transactions
- indexes

## Later Infrastructure

- Docker
- CI/CD
- cloud deployment
- object storage
- data pipeline
- analytics database / warehouse

These should be introduced gradually.

---

# 4. Version Roadmap

## V0.1 — Foundation

### Goal

Understand the foundation of a business application.

### Concepts

- project structure
- REST API
- PostgreSQL
- relational tables
- primary keys
- foreign keys
- CRUD
- migrations
- frontend/backend communication

### Architecture

```text
React
  │
  ▼
FastAPI
  │
  ▼
SQLAlchemy
  │
  ▼
PostgreSQL
```

### Initial Entities

```text
users
customers
products
employees
```

### Features

- create customer
- view customers
- update customer
- deactivate customer
- create product
- view products
- basic employee records

### Learning Outcome

Understand how:

```text
Frontend action
      ↓
HTTP request
      ↓
API endpoint
      ↓
Business logic
      ↓
Database operation
```

---

# V0.2 — CRM Core

### Goal

Understand customer relationship management.

### Concepts

- leads
- contacts
- opportunities
- sales pipeline
- customer lifecycle
- entity relationships

### Entities

```text
customers
contacts
leads
opportunities
activities
```

### Business Flow

```text
Lead
 ↓
Qualified Lead
 ↓
Opportunity
 ↓
Won / Lost
 ↓
Customer
```

### Example Pipeline

```text
New
 ↓
Contacted
 ↓
Qualified
 ↓
Proposal
 ↓
Negotiation
 ↓
Won
```

### Features

- customer management
- lead management
- opportunity pipeline
- contact management
- notes
- follow-up activities
- opportunity value
- expected close date

### Learning Outcome

Understand that CRM represents the relationship and sales process surrounding customers, not simply a customer table.

---

# V0.3 — Sales ERP Module

### Goal

Connect CRM activity to actual business transactions.

### Concepts

- quotations
- sales orders
- order items
- invoices
- payments
- transactional integrity

### Entities

```text
quotes
quote_items

sales_orders
sales_order_items

invoices
invoice_items

payments
```

### Business Flow

```text
Opportunity
    ↓
Quotation
    ↓
Sales Order
    ↓
Invoice
    ↓
Payment
```

### Important Database Concepts

- database transactions
- foreign keys
- constraints
- unique constraints
- numeric precision
- rollback
- calculated totals

### Learning Outcome

Understand how business applications maintain transactional consistency.

---

# V0.4 — Inventory

### Goal

Connect sales transactions to physical business resources.

### Concepts

- stock
- warehouses
- inventory movements
- stock adjustments
- reservations
- stock levels

### Entities

```text
warehouses
warehouse_locations
inventory
inventory_transactions
stock_adjustments
```

### Important Design

Avoid relying only on:

```text
products.quantity = 100
```

Instead, introduce inventory transactions.

Example:

```text
Opening Stock       +100
Sale                 -10
Purchase             +50
Adjustment             -2
-------------------------
Current Stock        138
```

### Learning Outcome

Understand that business state can often be derived from a history of transactions.

---

# V0.5 — Purchasing

### Goal

Introduce the supplier side of ERP.

### Entities

```text
suppliers
purchase_orders
purchase_order_items
goods_receipts
supplier_invoices
supplier_payments
```

### Business Flow

```text
Supplier
   ↓
Purchase Order
   ↓
Goods Receipt
   ↓
Supplier Invoice
   ↓
Payment
```

### Combined ERP Flow

```text
Customer
   ↓
Sales Order
   ↓
Invoice
   ↓
Payment

Supplier
   ↓
Purchase Order
   ↓
Goods Receipt
   ↓
Inventory
```

### Learning Outcome

Understand buying and selling as connected business processes that affect inventory and cash.

---

# V0.6 — Employees, Organization & RBAC

### Goal

Introduce organizational structure and access control.

### Entities

```text
employees
departments
roles
permissions
user_roles
```

### Example Roles

```text
Admin
 ├── Users
 ├── Configuration
 └── Everything

Sales Manager
 ├── Customers
 ├── Leads
 ├── Opportunities
 └── Sales Orders

Sales Representative
 ├── Assigned Customers
 ├── Leads
 └── Opportunities

Warehouse Staff
 ├── Inventory
 └── Goods Receipts
```

### Concepts

- authentication
- authorization
- RBAC
- ownership
- permission checks
- data isolation

### Learning Outcome

Understand:

> Authentication = "Who are you?"

> Authorization = "What are you allowed to do?"

---

# V0.7 — Business Rules & Workflow Engine

### Goal

Move beyond CRUD and make the application behave like an actual business system.

### Example Order Lifecycle

```text
Draft
 ↓
Submitted
 ↓
Approved
 ↓
Processing
 ↓
Shipped
 ↓
Completed
```

### Example Rules

- Cannot ship an unpaid order.
- Cannot sell an inactive product.
- Cannot approve an order with zero items.
- Cannot receive goods without a purchase order.
- Cannot exceed available inventory unless backorders are enabled.

### New Concepts

- state machines
- workflow transitions
- validation rules
- approval processes
- domain services
- business invariants

### Learning Outcome

Understand that enterprise applications are primarily about enforcing business processes, not just performing CRUD.

---

# V0.8 — Audit Trail & Activity History

### Goal

Make business actions traceable.

### Entities

```text
audit_logs
activity_logs
entity_history
```

### Example

```text
Order #1001

10:01  Created by Ralph
10:05  Submitted
10:12  Approved by Manager
11:30  Shipped by Warehouse
14:20  Completed
```

### Concepts

- auditability
- actor tracking
- timestamps
- entity history
- before/after values
- compliance-oriented design

### Learning Outcome

Understand why enterprise systems need to answer:

> Who changed what, when, and from what value to what value?

---

# V0.9 — Reporting Inside the ERP/CRM

### Goal

Introduce operational reporting before building a separate analytics pipeline.

### Reports

- sales today
- monthly revenue
- unpaid invoices
- top customers
- low-stock products
- open opportunities
- purchase spending
- employee activity

### Concepts

- SQL aggregation
- JOINs
- GROUP BY
- filtering
- date grouping
- KPI definitions

### Example

```sql
Revenue
= SUM(invoice_items.quantity * invoice_items.unit_price)
```

### Learning Outcome

Understand how raw transactional tables become business metrics.

---

# V1.0 — Production-Ready ERP/CRM Core

At this point the system should contain:

```text
CRM
 ├── Customers
 ├── Contacts
 ├── Leads
 ├── Opportunities
 └── Activities

Sales
 ├── Quotes
 ├── Orders
 ├── Invoices
 └── Payments

Inventory
 ├── Warehouses
 ├── Stock
 ├── Movements
 └── Adjustments

Purchasing
 ├── Suppliers
 ├── Purchase Orders
 ├── Goods Receipts
 └── Supplier Invoices

Organization
 ├── Employees
 ├── Departments
 ├── Roles
 └── Permissions

Platform
 ├── Authentication
 ├── RBAC
 ├── Workflows
 ├── Audit Logs
 └── Reporting
```

This becomes the stable operational foundation.

---

# 5. V1.1 — Data Extraction Layer

### Goal

Learn how data leaves an operational application.

Do not immediately build a huge data warehouse.

Start with controlled extraction.

```text
PostgreSQL
     ↓
Extraction Job
     ↓
Raw Export
```

### Concepts

- ETL
- ELT
- batch extraction
- incremental extraction
- timestamps
- watermarks
- change detection

### Example

```text
Extract:
orders created/updated since last run
```

### Learning Outcome

Understand how an analytics system obtains data without interfering with the ERP.

---

# V1.2 — Data Pipeline

### Goal

Build a real transformation pipeline.

```text
ERP PostgreSQL
      ↓
Extract
      ↓
Raw Layer
      ↓
Transform
      ↓
Validated Data
      ↓
Analytics Layer
```

### Transformations

Examples:

- normalize dates
- standardize categories
- calculate revenue
- join customers and orders
- remove duplicates
- create derived fields

### Concepts

- pipeline stages
- idempotency
- retries
- pipeline logs
- data freshness
- incremental processing

---

# V1.3 — Data Quality Integration

This is where your existing **Visiq Data Quality engine** becomes relevant.

### Architecture

```text
ERP PostgreSQL
      ↓
Data Pipeline
      ↓
Raw Data
      ↓
Data Quality
 ┌────────────────────┐
 │ Profile             │
 │ Validate            │
 │ Score               │
 │ Clean               │
 │ Lineage             │
 └──────────┬─────────┘
            ↓
       Trusted Data
```

### Quality Checks

- missing values
- duplicates
- invalid formats
- invalid dates
- numeric ranges
- categorical inconsistencies
- suspicious outliers
- type problems

### Important Principle

The quality layer should not silently corrupt the source ERP database.

```text
ERP data
   ↓
Raw copy
   ↓
Quality assessment
   ↓
Derived clean data
```

### Learning Outcome

Understand data quality as a pipeline stage rather than merely a spreadsheet-cleaning utility.

---

# V1.4 — Analytical Data Model

### Goal

Move from raw operational tables toward analytics-friendly structures.

Introduce:

- fact tables
- dimension tables
- star schema
- slowly changing dimensions later

### Example

```text
                 dim_customer
                      │
                      │
dim_date ───── fact_sales ───── dim_product
                      │
                      │
                dim_employee
```

### Fact Table Example

```text
fact_sales
----------
date_key
customer_key
product_key
employee_key
quantity
unit_price
discount
revenue
```

### Dimensions

```text
dim_customer
dim_product
dim_date
dim_employee
```

### Learning Outcome

Understand why the database used by an ERP is not necessarily the best structure for analytics.

---

# V1.5 — Power BI Integration

### Goal

Connect the analytical model to Power BI.

```text
ERP
 ↓
PostgreSQL
 ↓
ETL
 ↓
Data Quality
 ↓
Analytics Model
 ↓
Power BI
```

### Initial dashboards

#### Executive

- Revenue
- Orders
- Profit
- Customer growth
- Sales trend

#### Sales

- pipeline value
- conversion rate
- sales by representative
- top customers

#### Inventory

- current stock
- stock turnover
- low-stock products
- inventory movement

#### Purchasing

- supplier spending
- purchase trends
- supplier performance

### Concepts

- semantic models
- measures
- DAX
- calculated columns
- relationships
- filter context
- KPI design

---

# V1.6 — Visiq Integration

Now connect your existing AI Data Analyst platform.

```text
                         ┌── Power BI
                         │
ERP → PostgreSQL → ETL → Quality → Analytics
                         │
                         └── Visiq
```

### Visiq responsibilities

Visiq can answer questions such as:

```text
"Why did revenue decrease last month?"

"Which customers generated the most revenue?"

"Which products are declining?"

"Show me year-over-year sales trends."

"Are there quality issues affecting this report?"

"Which region has the highest growth?"
```

### AI architecture

```text
User Question
      ↓
Visiq Agent
      ↓
Intent / Routing
      ↓
Tool Selection
      ↓
Analytics / Data Quality Tools
      ↓
Deterministic Computation
      ↓
LLM Explanation
      ↓
Chart + Insight
```

### Important Principle

The LLM should not invent the numbers.

```text
Database / Tool
      ↓
Actual result
      ↓
LLM explanation
```

---

# V1.7 — AI-Assisted ERP Features

Only after the core ERP and analytics architecture works should AI be introduced into the ERP itself.

### Possible features

- lead summarization
- customer interaction summaries
- sales opportunity suggestions
- natural-language report generation
- invoice explanation
- anomaly explanations
- inventory alerts
- natural-language search

### Example

```text
User:
"Which customers have not purchased anything in the
last 90 days?"

AI
 ↓
Query tool
 ↓
Database
 ↓
Actual records
 ↓
Explanation
```

AI remains an assistant over deterministic business systems.

---

# V1.8 — Notifications & Automation

### Goal

Introduce event-driven thinking.

### Example

```text
Inventory falls below threshold
          ↓
Event
          ↓
Notification
          ↓
Warehouse / Manager
```

Other examples:

```text
Invoice overdue
      ↓
Reminder

Opportunity close date approaching
      ↓
Sales notification

Purchase order delayed
      ↓
Operations alert
```

### Concepts

- events
- background jobs
- queues
- scheduled tasks
- notifications
- retry mechanisms

---

# V1.9 — DevOps & Deployment

### Goal

Make the platform deployable and maintainable.

### Architecture

```text
Developer
   ↓
Git
   ↓
GitHub
   ↓
CI
 ├── Tests
 ├── Lint
 ├── Build
 └── Security checks
   ↓
CD
   ↓
Deployment
```

### Introduce

- Docker
- environment variables
- CI/CD
- migrations
- staging
- production
- logging
- monitoring
- backups

---

# V2.0 — Integrated Business Intelligence Platform

Final conceptual architecture:

```text
                           ┌──────────────────┐
                           │   ERP / CRM      │
                           │                  │
                           │ Customers        │
                           │ Sales            │
                           │ Inventory        │
                           │ Purchasing      │
                           │ Employees        │
                           └────────┬─────────┘
                                    │
                                    ▼
                           ┌──────────────────┐
                           │   PostgreSQL     │
                           │ Operational DB   │
                           └────────┬─────────┘
                                    │
                                    ▼
                           ┌──────────────────┐
                           │   ETL / ELT      │
                           │ Data Pipeline    │
                           └────────┬─────────┘
                                    │
                                    ▼
                           ┌──────────────────┐
                           │  Data Quality    │
                           │                  │
                           │ Profile          │
                           │ Validate         │
                           │ Clean            │
                           │ Score            │
                           │ Lineage          │
                           └────────┬─────────┘
                                    │
                                    ▼
                           ┌──────────────────┐
                           │ Analytics Model  │
                           │                  │
                           │ Facts            │
                           │ Dimensions       │
                           │ KPIs             │
                           └────────┬─────────┘
                                    │
                       ┌────────────┴────────────┐
                       │                         │
                       ▼                         ▼
                ┌──────────────┐          ┌──────────────┐
                │   Power BI   │          │    Visiq     │
                │ BI / DAX     │          │ AI Analyst   │
                └──────┬───────┘          └──────┬───────┘
                       │                         │
                       └────────────┬────────────┘
                                    ▼
                           Business Decisions
```

---

# 6. Version-to-Concept Map

| Version | Main Concept |
|---|---|
| V0.1 | REST + PostgreSQL + CRUD |
| V0.2 | CRM |
| V0.3 | Sales transactions |
| V0.4 | Inventory |
| V0.5 | Purchasing |
| V0.6 | Authentication + RBAC |
| V0.7 | Business rules + workflows |
| V0.8 | Audit trails |
| V0.9 | SQL reporting + KPIs |
| V1.0 | Complete operational ERP/CRM |
| V1.1 | Data extraction |
| V1.2 | ETL / ELT |
| V1.3 | Data Quality |
| V1.4 | Analytics data modeling |
| V1.5 | Power BI + DAX |
| V1.6 | Visiq integration |
| V1.7 | AI-assisted ERP |
| V1.8 | Events + automation |
| V1.9 | Docker + CI/CD + deployment |
| V2.0 | Integrated business intelligence platform |

---

# 7. Development Rule

Do not implement every version at once.

For every version:

```text
1. Learn the business concept
        ↓
2. Design the data model
        ↓
3. Implement backend
        ↓
4. Implement API
        ↓
5. Implement frontend
        ↓
6. Test
        ↓
7. Generate realistic data
        ↓
8. Explain the architecture
        ↓
9. Review
        ↓
10. Move to next version
```

The user should be able to explain the version before moving forward.

---

# 8. Definition of Done

A version is not complete simply because the UI works.

Each version should have:

- working database schema
- migrations
- API endpoints
- frontend workflow
- validation
- business rules where applicable
- tests
- realistic sample data
- documentation
- architecture explanation
- known limitations

---

# 9. What Should NOT Be Built Too Early

Avoid prematurely adding:

- microservices
- Kubernetes
- Kafka
- complex cloud infrastructure
- distributed databases
- advanced AI agents
- machine learning models
- full accounting systems
- payroll
- manufacturing
- multi-country tax systems

These can be explored later if the core system actually requires them.

The goal is:

> **Understand the architecture before increasing the complexity.**

---

# 10. Final Learning Outcome

By completing the roadmap, the project should demonstrate understanding of:

### Application Engineering

- React
- REST APIs
- FastAPI
- authentication
- RBAC
- business logic
- testing

### Database Engineering

- PostgreSQL
- relational modeling
- normalization
- transactions
- indexes
- constraints
- SQL

### ERP / CRM

- customers
- leads
- opportunities
- sales
- purchasing
- inventory
- employees
- workflows

### Data Engineering

- extraction
- ETL / ELT
- incremental pipelines
- data validation
- lineage
- analytical modeling

### Data Analytics

- KPIs
- SQL analytics
- Power BI
- DAX
- star schemas
- dashboards

### AI Engineering

- tool calling
- deterministic computation
- RAG where appropriate
- AI-assisted workflows
- natural-language analytics
- AI safety boundaries

### DevOps

- Git
- CI/CD
- Docker
- deployment
- logging
- monitoring
- backups

The final project is therefore not just an ERP/CRM application.

It becomes a complete demonstration of the path:

```text
BUSINESS
   ↓
ERP / CRM
   ↓
OPERATIONAL DATA
   ↓
DATABASE
   ↓
DATA ENGINEERING
   ↓
DATA QUALITY
   ↓
ANALYTICS MODEL
   ↓
BI + AI
   ↓
BUSINESS DECISIONS
```

This is the central architecture that should guide the entire project.
