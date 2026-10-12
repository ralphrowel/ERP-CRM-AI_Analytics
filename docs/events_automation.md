# Events, Notifications & Automation Guide (Milestone V1.8)

## 1. Overview & Architecture

In an enterprise ERP/CRM system, operations such as order confirmation, approval routing, inventory thresholds, and invoice aging have side effects (sending emails, pushing alerts, notifying assignees).

Directly invoking external services (such as SMTP servers or webhooks) within the scope of an HTTP request introduces severe vulnerabilities:
1. **Partial Failures & Inconsistency**: If the database transaction commits but the network request fails, or vice versa, the system state diverges.
2. **High Latency & Slow HTTP Responses**: Network timeouts to SMTP or external APIs stall client HTTP threads.
3. **Loss of Telemetry on Failures**: Without persistent state, temporary email server outages lose critical customer notifications.

Milestone V1.8 implements the **Transactional Outbox Pattern**:

```
[ HTTP Request / Business Logic ]
           |
           v
+------------------------------------------+
|          Database Transaction            |
|  1. Mutate Domain Entity (e.g. Invoice)  |
|  2. Append Event to `outbox_events`      |
+------------------------------------------+
                     | (Committed together atomically)
                     v
             [ PostgreSQL / DB ]
                     |
                     | (Polled via SELECT ... FOR UPDATE SKIP LOCKED)
                     v
            [ Outbox Worker Process ]
           /         |             \
          v          v              v
   [In-App Notif] [SMTP Mailer] [Cron Automation]
```

---

## 2. Database Schema

### `outbox_events`
- `id`: BigInteger Primary Key.
- `event_type`: String (e.g. `approval_request.created`, `password_reset.requested`, `inventory.below_reorder`).
- `aggregate_type`: String (`approval_request`, `user`, `product`, `invoice`, etc.).
- `aggregate_id`: BigInteger foreign entity ID.
- `payload`: JSON data containing contextual metadata.
- `attempts`: SmallInteger tracking retry count (0 to 8).
- `available_at`: DateTime when this event can be claimed next (implements exponential backoff).
- `processed_at`: DateTime of successful completion (NULL while pending).
- `last_error`: Text trace of the most recent failure exception.
- `created_at`: DateTime event was enqueued.

### `notifications`
- `id`: BigInteger Primary Key.
- `user_id`: BigInteger recipient ID.
- `title`: String short alert title.
- `message`: Text message body.
- `link`: Optional relative URL (e.g. `/sales/invoices/12`).
- `category`: String classification (`sales`, `purchasing`, `inventory`, `workflow`, `system`).
- `is_read`: Boolean read status flag.
- `read_at`: DateTime when marked as read.
- `dedup_key`: Unique deduplication key preventing duplicate alerts for identical occurrences.

---

## 3. Worker Execution & Resilience Guarantees

### At-Least-Once Delivery & Idempotency
- The worker claims batches of uncompleted events where `processed_at IS NULL` and `available_at <= NOW()` and `attempts < 8`.
- If a worker crashes or is forcefully terminated mid-execution, uncommitted events remain available and are re-claimed upon worker restart.
- All handlers use idempotent logic (e.g., checking for existing notifications or utilizing `dedup_key`).

### Exponential Backoff
When a handler raises an unhandled exception:
$$\text{delay} = 2^{\text{attempts}} \text{ seconds}$$
- Attempt 1: delay 2s
- Attempt 2: delay 4s
- Attempt 3: delay 8s
- ...
- Attempt 7: delay 128s

### Dead-Letter Observability
If an event fails `MAX_OUTBOX_ATTEMPTS` (8 attempts):
- The event is quarantined with `attempts = 8`.
- It will no longer be claimed by regular polling workers.
- Administrators can review the event and exception trace in `/api/v1/events/dead-letters` or via the frontend "Outbox Dead-Letters" tab.
- An administrator can trigger an immediate replay via `POST /api/v1/events/dead-letters/{id}/retry`.

---

## 4. Scheduled Checks Engine (Daily Cron Checks)

The `ScheduledChecksEngine` runs 5 automated checks across core business domains:
1. `sales.invoice_past_due`: Invoices with `balance_due > 0` and `due_date < today`.
2. `sales.quote_expired`: Quotes in `sent` status where `valid_until < today`.
3. `crm.opportunity_closing_soon`: Deals in active stages closing within the next 7 days.
4. `purchasing.po_delayed`: Purchase orders in `sent` or `partially_received` where `expected_date < today`.
5. `inventory.below_reorder`: Stockable items where total `qty_on_hand <= reorder_point`.

---

## 5. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/notifications` | Paginated in-app notifications with `unread_only` filter |
| `GET` | `/api/v1/notifications/unread-count` | Returns `{ unread_count: N }` for nav badges |
| `PATCH` | `/api/v1/notifications/{id}/read` | Mark individual notification as read |
| `POST` | `/api/v1/notifications/read-all` | Mark all user notifications as read |
| `GET` | `/api/v1/events/dead-letters` | List dead-letter events (Superuser only) |
| `POST` | `/api/v1/events/dead-letters/{id}/retry` | Re-queue dead-letter event for immediate retry |
