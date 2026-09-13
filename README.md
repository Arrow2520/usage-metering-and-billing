# FlyRank Capstone: Usage Metering & Billing Engine

This repository contains the backend service for a SaaS usage metering and billing engine. It is designed to track API and AI token usage, enforce quotas, calculate costs, and integrate with Stripe in test mode.

---

## 1. Database Schema

The database model ensures strict tenant isolation and idempotent usage tracking. The core tables are:

* `tenants`
* `plans`
* `subscriptions`
* `usage_events`

### `plans`

Defines the subscription tiers and their hard limits.

| Column               | Type      | Description                 |
| :------------------- | :-------- | :-------------------------- |
| **id**               | UUID (PK) | Unique identifier           |
| **name**             | VARCHAR   | Plan name (e.g., Free, Pro) |
| **api_call_limit**   | INTEGER   | Max API calls per month     |
| **ai_token_limit**   | INTEGER   | Max AI tokens per month     |
| **base_price_cents** | INTEGER   | Monthly cost in cents       |

### `tenants`

Represents customer organizations. Data is isolated per tenant.

| Column                 | Type      | Description                 |
| :--------------------- | :-------- | :-------------------------- |
| **id**                 | UUID (PK) | Unique identifier           |
| **name**               | VARCHAR   | Tenant organization name    |
| **stripe_customer_id** | VARCHAR   | Stripe reference (nullable) |
| **created_at**         | TIMESTAMP | Record creation date        |

### `subscriptions`

Mirrors the payment truth from Stripe via verified webhook events.

| Column                     | Type      | Description                            |
| :------------------------- | :-------- | :------------------------------------- |
| **id**                     | UUID (PK) | Unique identifier                      |
| **tenant_id**              | UUID (FK) | References `tenants`                   |
| **plan_id**                | UUID (FK) | References `plans`                     |
| **stripe_subscription_id** | VARCHAR   | Stripe subscription reference          |
| **status**                 | VARCHAR   | e.g., `active`, `past_due`, `canceled` |
| **current_period_start**   | TIMESTAMP | Start of billing cycle                 |
| **current_period_end**     | TIMESTAMP | End of billing cycle                   |

### `usage_events`

An append-only ledger for exactly-once metering.

| Column              | Type      | Description                            |
| :------------------ | :-------- | :------------------------------------- |
| **id**              | UUID (PK) | Unique identifier                      |
| **tenant_id**       | UUID (FK) | References `tenants`                   |
| **usage_type**      | VARCHAR   | `api_call` or `ai_token`               |
| **quantity**        | INTEGER   | Amount of usage consumed               |
| **idempotency_key** | VARCHAR   | Unique string for deduplication        |
| **metadata**        | JSONB     | Token breakdown (cached vs. reasoning) |
| **created_at**      | TIMESTAMP | Event timestamp                        |

---

## 2. Plans & Quotas

The system enforces limits before allowing a billable action. The available plans are:

### Free Plan

* **API Calls:** 1,000 / month
* **AI Tokens:** 100,000 / month
* **Cost:** $0.00 / month

### Pro Plan

* **API Calls:** 10,000 / month
* **AI Tokens:** 5,000,000 / month
* **Cost:** $20.00 / month (2,000 cents)

---

## 3. Metering API Contract

The primary billable endpoint tracks simulated AI usage without requiring a live AI model key.

### Endpoint

```http
POST /generate
```

### Headers

```http
Authorization: Bearer <tenant_api_key>
Idempotency-Key: <unique_uuid>
```

### Request Payload

```json
{
  "prompt": "Write a story about a fox.",
  "simulated_usage": {
    "input_tokens": 500,
    "cached_input_tokens": 2000,
    "output_tokens": 1500,
    "reasoning_tokens": 500
  }
}
```

### Success Response

**`200 OK`**

```json
{
  "status": "success",
  "message": "Generated successfully",
  "usage_recorded": true
}
```

### Boundary Responses

| Status Code               | Meaning                                                                 |
| :------------------------ | :---------------------------------------------------------------------- |
| **429 Too Many Requests** | Usage quota exceeded                                                    |
| **402 Payment Required**  | Upgrade or payment required, e.g., subscription is past due or canceled |

---

## 4. Idempotency Strategy

To guarantee that the same request retry records exactly one usage event, the system utilizes a unique database constraint.

### 1. Composite Constraint

The `usage_events` table enforces a unique constraint on:

```text
(tenant_id, idempotency_key)
```

This ensures that the same tenant cannot record multiple usage events using the same idempotency key.

### 2. Duplicate Handling

If a client retries a request with an existing `Idempotency-Key`, the database raises a unique constraint violation.

### 3. Safe Return

The API catches this violation, skips creating a duplicate usage event, and safely returns the original success response.

---

## 5. Token Pricing Logic (Cost Calculation)

To accurately calculate monthly costs, the engine implements specific pricing rules for different AI token categories. The pricing constants are pinned in the application configuration and calculate the final cost as follows:

**Pricing Constants (per 1,000,000 tokens):**
*   **Standard Input Tokens:** $1.50
*   **Cached Input Tokens:** $0.15 *(Cheaper than standard input)*
*   **Output Tokens:** $9.00
*   **Reasoning Tokens:** $9.00 *(Billed at the same rate as output tokens)*

**Calculation Rule:**
`Total Cost = (Input Cost) + (Cached Input Cost) + (Output Cost) + (Reasoning Cost)`

*Note: Token categories cannot simply be added together before calculating the price, as they have different weights. The backend calculates the fractional cent cost for each category and rolls them up into the tenant's monthly total.*

## Summary

The FlyRank billing engine provides:

* **Multi-tenant isolation** through tenant-scoped data.
* **Usage metering** for API calls and AI tokens.
* **Quota enforcement** before billable actions.
* **Idempotent usage tracking** using database-level uniqueness constraints.
* **Subscription management** synchronized with Stripe webhooks.
* **Simulated AI usage** for testing without requiring a live AI model.
* **HTTP-level billing boundaries** using `429` and `402` responses.
