# Usage Metering & Billing Engine — Evidence

This document provides reproducible evidence for the implementation and validation
of the FlyRank Usage Metering & Billing Engine.

---

## 1. Metering — Idempotency

**Requirement:** The same billable request must not be counted more than once
when retried with the same idempotency key.

The automated test suite verifies that the first request is recorded and that a
retry with the same tenant and idempotency key is deduplicated without creating
additional usage events.

### Pytest evidence

```text
tests/test_idempotency.py::test_first_request_records_usage PASSED
tests/test_idempotency.py::test_duplicate_request_is_deduplicated PASSED
```

The test also verifies the ledger contents:

```text
First request:
- 1 api_call usage event
- 1 ai_token usage event
- Total events: 2

Duplicate request:
- Response status: deduplicated
- Total events remain: 2
```

The database additionally enforces a composite uniqueness constraint on
`(tenant_id, idempotency_key)`.

---

## 2. Quota Enforcement

**Requirement:** Usage must be rejected at quota boundaries with the correct
HTTP status codes.

### API-call quota

The test preloads exactly the Free-plan API-call limit of 1,000 calls and
attempts one additional billable request.

```text
tests/test_quota.py::test_api_call_quota_returns_429 PASSED
```

Expected boundary response:

```text
HTTP 429 Too Many Requests
API call quota exceeded
```

### AI-token quota

The test preloads exactly 100,000 AI tokens and attempts one additional token.

```text
tests/test_quota.py::test_ai_token_quota_returns_429 PASSED
```

Expected boundary response:

```text
HTTP 429 Too Many Requests
AI token quota exceeded
```

### Inactive subscription states

The following subscription states are verified to return `402 Payment Required`:

```text
past_due
canceled
unpaid
expired
incomplete
```

Pytest evidence:

```text
tests/test_quota.py::test_inactive_subscription_returns_402[past_due] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[canceled] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[unpaid] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[expired] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[incomplete] PASSED
```

Each test verifies:

```text
HTTP 402 Payment Required
Active subscription required
```

---

## 3. Cost Calculation

**Requirement:** AI token categories must be billed using their individual
pricing rules, including cheaper cached input tokens and reasoning tokens
billed at the output rate. Monetary arithmetic is performed using integer
micro-cents rather than floating-point values.

### Configured pricing

The application stores the following rates in `app/config.py`:

```text
API call:             10,000 micro-cents
Standard input:          100 micro-cents/token
Cached input:             50 micro-cents/token
Output:                  400 micro-cents/token
Reasoning:               400 micro-cents/token
```

The cached-input rate is lower than the standard-input rate, while reasoning
uses the same rate as output.

### Deterministic pricing calculation

The standard pytest payload contains:

```json
{
  "api_calls": 1,
  "input_tokens": 100,
  "cached_input_tokens": 50,
  "output_tokens": 100,
  "reasoning_tokens": 50
}
```

Total AI tokens:

```text
100 + 50 + 100 + 50 = 300 tokens
```

Cost calculation:

```text
API call:
1 × 10,000 = 10,000 micro-cents

Standard input:
100 × 100 = 10,000 micro-cents

Cached input:
50 × 50 = 2,500 micro-cents

Output:
100 × 400 = 40,000 micro-cents

Reasoning:
50 × 400 = 20,000 micro-cents

Total:
82,500 micro-cents
= 8 cents after conversion to integer cents
```

Therefore, for this isolated one-request example:

```json
{
  "used": {
    "api_calls": 1,
    "ai_tokens": 300
  },
  "cost_cents": 8
}
```

The `/usage` endpoint aggregates the persisted usage ledger and returns
`used`, `limit`, and `cost_cents`. A live request to `/usage` returned HTTP
`200 OK`.

---

## 4. Stripe Integration

**Requirement:** Stripe test-mode checkout and webhook processing must update
the local subscription state.

### Automated Stripe tests

The final automated test run verifies:

```text
tests/test_stripe.py::test_create_checkout_session_success PASSED
tests/test_stripe.py::test_create_checkout_session_blocked_for_active_tenant PASSED
tests/test_stripe.py::test_webhook_checkout_completed_updates_db PASSED
```

The webhook test specifically verifies that a `checkout.session.completed`
event changes the local subscription to `active` and stores the Stripe
subscription ID.

### Stripe CLI evidence

Stripe CLI was configured to forward events to:

```text
http://localhost:8000/webhooks/stripe
```

The listener reported that it was ready and supplied a webhook signing secret.
The secret is intentionally not reproduced in this document.

A live Stripe test produced a `checkout.session.completed` event that was
successfully forwarded to the backend:

```text
2026-09-13 17:55:41   --> checkout.session.completed [event]
2026-09-13 17:55:41   <-- [200] POST http://localhost:8000/webhooks/stripe [event]
```

A later live checkout produced the same successful result:

```text
2026-09-13 23:25:08   --> checkout.session.completed [event]
2026-09-13 23:25:08   <-- [200] POST http://localhost:8000/webhooks/stripe [event]
```

The same Stripe flow also generated related subscription/payment events, and
the forwarded webhook requests returned HTTP `200`.

### PostgreSQL verification

The resulting local subscription state was verified directly in PostgreSQL:

```text
metering_db=# SELECT tenant_id, status, stripe_subscription_id FROM subscriptions;

tenant_id                               | status | stripe_subscription_id
----------------------------------------+--------+-------------------------
84caa45e-074f-4dd4-9e18-252105941268    | active | sub_1UFHcMH4OiqotMa2ctR2d3JI

(1 row)
```

This demonstrates that the local subscription was persisted with an `active`
status and a Stripe subscription reference.

---

## 5. Data Model & Persistence

**Requirement:** Tenants, plans, subscriptions, and usage events must be
persisted in PostgreSQL with tenant-scoped usage tracking.

### Core tables

The PostgreSQL schema contains:

```text
plans
tenants
subscriptions
usage_events
```

The `usage_events` table stores:

```text
tenant_id
usage_type
quantity
idempotency_key
metadata (JSONB)
created_at
```

The `metadata` JSONB field stores the individual AI token categories needed for
accurate cost calculation.

### Subscription persistence

The active subscription was verified in PostgreSQL:

```text
tenant_id                               | status | stripe_subscription_id
----------------------------------------+--------+-------------------------
84caa45e-074f-4dd4-9e18-252105941268    | active | sub_1UFHcMH4OiqotMa2ctR2d3JI
```

### Database-level idempotency

The schema defines the following uniqueness constraint:

```text
uq_tenant_idempotency
UNIQUE (tenant_id, idempotency_key)
```

This provides database-level protection against duplicate usage records.

---

## 6. Final Automated Test Suite

The final test run completed successfully:

```text
PS F:\Usage Metering and Billing Engine> pytest -v

======================================================== test session starts =========================================================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: F:\Usage Metering and Billing Engine
plugins: anyio-4.15.1
collected 12 items

tests/test_idempotency.py::test_first_request_records_usage PASSED
tests/test_idempotency.py::test_duplicate_request_is_deduplicated PASSED
tests/test_quota.py::test_api_call_quota_returns_429 PASSED
tests/test_quota.py::test_ai_token_quota_returns_429 PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[past_due] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[canceled] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[unpaid] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[expired] PASSED
tests/test_quota.py::test_inactive_subscription_returns_402[incomplete] PASSED
tests/test_stripe.py::test_create_checkout_session_success PASSED
tests/test_stripe.py::test_create_checkout_session_blocked_for_active_tenant PASSED
tests/test_stripe.py::test_webhook_checkout_completed_updates_db PASSED

================================================== 12 passed, 2 warnings in 6.10s ===================================================
```

The two warnings are dependency deprecation warnings from the FastAPI/Starlette
test-client stack and did not cause any test failures.

---

## 7. FastAPI Runtime Evidence

The application was successfully started in development mode:

```text
FastAPI development server started
Server: http://127.0.0.1:8000
Documentation: http://127.0.0.1:8000/docs
Application startup complete.
```

The runtime logs also show successful requests to the main billable and usage
endpoints:

```text
127.0.0.1 - "GET /docs HTTP/1.1" 200
127.0.0.1 - "GET /openapi.json HTTP/1.1" 200
127.0.0.1 - "POST /generate HTTP/1.1" 200
127.0.0.1 - "GET /usage HTTP/1.1" 200
```

---

## 8. Evidence Summary

The collected evidence demonstrates:

- Exactly-once usage recording through tenant-scoped idempotency keys.
- Database-level uniqueness protection for duplicate requests.
- API-call quota enforcement with HTTP `429`.
- AI-token quota enforcement with HTTP `429`.
- Inactive subscription protection with HTTP `402`.
- Granular token metadata for input, cached input, output, and reasoning tokens.
- Integer micro-cent pricing arithmetic to avoid floating-point currency errors.
- Stripe test-mode checkout and webhook processing.
- PostgreSQL persistence of subscription and Stripe state.
- Automated regression coverage across metering, quotas, and Stripe integration.
- A final automated test result of **12 passed**.
