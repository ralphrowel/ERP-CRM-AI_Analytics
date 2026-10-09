# Consolidated Business Rules Register

This document registers all operational business invariants and rules enforced across the ERP/CRM system, referencing their automated test coverage (Roadmap V0.7 §4.7).

---

## 1. CRM Module (`crm`)

| Rule ID | Entity | Description | Invariant / Constraint | Error Code | Test Reference |
|---|---|---|---|---|---|
| `BR-CRM-001` | Customer | Customer code format & uniqueness | `customer_no` unique, pattern `CUSxxxxxx` | `DB_INTEGRITY_ERROR` | `test_purchasing_orders.py` |
| `BR-CRM-002` | Customer | Prospect to Active on first sale | Customer with status `prospect` transitions to `active` upon confirmation of their first sales order | N/A (State Effect) | `test_sales_order_from_quote_and_confirm` |
| `BR-CRM-003` | Lead | Direct conversion disallowed | Lead can only be converted via `/convert` endpoint | `INVALID_TRANSITION` | `test_crm_transitions.py` |
| `BR-CRM-004` | Lead | Transition Matrix Enforcement | Status follows state machine (`new` → `contacted` → `qualified` → `converted` / `disqualified`) | `INVALID_LEAD_TRANSITION` | `test_crm_transitions.py` |
| `BR-CRM-005` | Lead | Disqualification Reason Required | Disqualifying a lead requires non-empty reason string | `REASON_REQUIRED` | `test_crm_transitions.py` |
| `BR-CRM-006` | Opportunity | Stage Pipeline Flow | Stages flow sequentially or branch to `lost` | `INVALID_STAGE_TRANSITION` | `test_crm_transitions.py` |
| `BR-CRM-007` | Opportunity | Auto-Win on Accepted Quote | Opportunity automatically moves to `won` when linked quote is accepted | N/A (Side Effect) | `test_quote_linked_opportunity_auto_win` |

---

## 2. Sales & Commercial Commitments (`sales`)

| Rule ID | Entity | Description | Invariant / Constraint | Error Code | Test Reference |
|---|---|---|---|---|---|
| `BR-SALES-001` | Quote / Order | Non-Negative Money Math | Unit prices, line totals, and subtotals must be non-negative; discount <= subtotal | `INVALID_DISCOUNT` | `test_calculate_line_invalid_discount` |
| `BR-SALES-002` | Quote / Order | Half-Up Monetary Rounding | Standard currency rounding to 2 decimals using `ROUND_HALF_UP` | N/A (Math Module) | `test_round_money_half_up` |
| `BR-SALES-003` | Quote | Immutable Line Snapshots | Accepted/Sent quote cannot modify unit prices, discounts, or tax snapshots | `CANNOT_MODIFY_SENT_QUOTE` | `test_quote_lifecycle_and_snapshots` |
| `BR-SALES-004` | Quote | Expiration Enforcement | Expired quotes cannot be accepted or converted to sales orders | `QUOTE_EXPIRED` | `test_quote_expiration_check` |
| `BR-SALES-005` | Sales Order | Active Items Only | Order confirmation rejected if customer is inactive or contains inactive products | `CUSTOMER_INACTIVE` / `PRODUCT_INACTIVE` | `test_sales_commitments.py` |
| `BR-SALES-006` | Sales Order | Credit Limit Enforcement | Total exposure (open AR + uninvoiced orders + current order) cannot exceed `customer.credit_limit` unless approved | `CREDIT_LIMIT_EXCEEDED` | `test_credit_limit_exceeded_rejection` |
| `BR-SALES-007` | Sales Order | Discount Threshold Approval | If order discount > 15%, confirmation creates `ApprovalRequest` (`SO_DISCOUNT`) and pauses in `pending_approval` | `APPROVAL_REQUIRED` | `test_workflow_approval_discount` |
| `BR-SALES-008` | Sales Order | Stock Reservation on Confirm | Confirming physical sales order automatically reserves inventory in warehouse | `INSUFFICIENT_STOCK` | `test_insufficient_stock_rejection` |
| `BR-SALES-009` | Sales Order | Cancellation Stock Release | Cancelling confirmed sales order releases reserved inventory allocations | N/A (Side Effect) | `test_cancel_order_releases_reservations` |
| `BR-SALES-010` | Sales Order | Prepaid Enforcement | Prepaid terms require invoice issuance and full settlement before shipment creation | `PREPAID_UNPAID` | `test_prepaid_rule_enforcement` |

---

## 3. Financial Obligations & AR (`sales`)

| Rule ID | Entity | Description | Invariant / Constraint | Error Code | Test Reference |
|---|---|---|---|---|---|
| `BR-FIN-001` | Invoice | Immutable Line Snapshots | Issuing an invoice freezes customer legal obligation; no edits permitted | `INVOICE_NOT_EDITABLE` | `test_financial_obligations.py` |
| `BR-FIN-002` | Invoice | Partial Invoicing Allowed | An order may have multiple partial invoices up to total ordered quantity | `EXCEEDS_ORDERED_QTY` | `test_partial_invoicing_workflow` |
| `BR-FIN-003` | Payment | Payment Allocation Limit | Total payment allocations cannot exceed payment unallocated amount or invoice balance | `ALLOCATION_EXCEEDS_BALANCE` | `test_payment_allocations_and_derived_invoice_status` |
| `BR-FIN-004` | Payment | Void Payment Balance Restore | Voiding a payment restores invoice balance due and adjusts invoice status | N/A (Side Effect) | `test_void_payment_restores_invoice_balance` |
| `BR-FIN-005` | Credit Note | Max Credit Exposure | Credit notes cannot exceed invoice issued amount | `CREDIT_NOTE_EXCEEDS_BALANCE` | `test_credit_note_reduces_balance` |
| `BR-FIN-006` | Idempotency | Idempotency Key Replay | Same `Idempotency-Key` returns identical cached payload without re-executing | `CONFLICT` | `test_idempotency_replay_and_conflict` |

---

## 4. Inventory, Costing & Fulfillment (`inventory`)

| Rule ID | Entity | Description | Invariant / Constraint | Error Code | Test Reference |
|---|---|---|---|---|---|
| `BR-INV-001` | Balance | Non-Negative Available Stock | `quantity_available = quantity_on_hand - quantity_reserved >= 0` | `INSUFFICIENT_STOCK` | `test_insufficient_stock_rejection` |
| `BR-INV-002` | Service | Service Items Bypass Stock | Services do not hold inventory balances or create stock reservations | N/A (Logic Bypass) | `test_service_product_bypasses_reservation` |
| `BR-INV-003` | Shipment | COGS Snapshot on Dispatch | Dispatched shipments calculate and snapshot COGS using Weighted Average Cost (WAC) | N/A (Costing Effect) | `test_shipment_lifecycle_and_cogs_snapshot` |
| `BR-INV-004` | Order | Completion Invariant | Order status marked `completed` only when fully shipped AND fully invoiced | N/A (Derived Status) | `test_order_completion_when_fully_shipped_and_fully_invoiced` |
| `BR-INV-005` | Stock Adjustment | Spend Limit Approval | Stock adjustment with absolute total value > ₱20,000 requires managerial approval (`ADJ_VALUE`) | `APPROVAL_REQUIRED` | `test_workflow_approval_stock_adj` |

---

## 5. Procurement & Purchasing (`purchasing`)

| Rule ID | Entity | Description | Invariant / Constraint | Error Code | Test Reference |
|---|---|---|---|---|---|
| `BR-PURCH-001` | Purchase Order | Draft Modification Only | Purchase orders can only be updated while in `draft` status | `INVALID_STATUS_TRANSITION` | `test_purchase_order_update_in_draft` |
| `BR-PURCH-002` | Purchase Order | High-Value Spend Approval | PO with grand total > ₱100,000 requires `purchase_order:approve` under rule `PO_AMOUNT` | `APPROVAL_REQUIRED` | `test_workflow_approval_po_amount` |
| `BR-PURCH-003` | Purchase Order | Short-Close Invariant | Short-close is only permitted on `partially_received` purchase orders | `INVALID_STATUS_TRANSITION` | `test_purchase_order_short_close` |
| `BR-PURCH-004` | Goods Receipt | No Over-Receipt | Intake quantity cannot exceed PO item remaining unreceived quantity | `OVER_RECEIPT_NOT_ALLOWED` | `test_goods_receipt_over_receipt_rejection` |
| `BR-PURCH-005` | Goods Receipt | Weighted-Average Cost Update | Posting a goods receipt recalculates product WAC: `(old_val + new_val) / total_qty` | N/A (Math Snapshot) | `test_wac_recalculation_after_multiple_receipts` |
| `BR-PURCH-006` | Supplier Bill | 3-Way Match Verification | Bill line quantity must match goods receipts; price difference within 2% tolerance | `MATCH_EXCEPTION` | `test_supplier_invoice_3_way_match_quantity_exception` |
| `BR-PURCH-007` | Supplier Bill | Duplicate Invoice Reference | Vendor invoice reference must be unique per supplier | `DUPLICATE_SUPPLIER_INVOICE_REF` | `test_duplicate_supplier_invoice_ref_rejected` |

---

## 6. Workflow & Separation of Duties (`workflow`)

| Rule ID | Entity | Description | Invariant / Constraint | Error Code | Test Reference |
|---|---|---|---|---|---|
| `BR-WF-001` | Approval Request | Separation of Duties | Requester cannot decide (approve/reject) their own approval request | `SEPARATION_OF_DUTIES_VIOLATION` | `test_workflow_separation_of_duties` |
| `BR-WF-002` | Approval Request | Single Pending Request | Unique pending request per `(rule_id, entity_type, entity_id)` | `DB_INTEGRITY_ERROR` | `test_workflow_unique_pending_request` |
| `BR-WF-003` | Approval Request | Rejection Returns to Draft | Rejecting an approval request resets the document back to `draft` status | N/A (State Effect) | `test_workflow_rejection_resets_to_draft` |
| `BR-WF-004` | Approval Rule | DB Threshold Configuration | Approval rules and limits are read from DB dynamically without redeployment | N/A (Dynamic Resolution) | `test_workflow_dynamic_threshold_update` |
