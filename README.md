# FlyRank Capstone --- Usage Metering & Billing Engine

A small **FastAPI + PostgreSQL** backend for SaaS usage metering and
billing. The service tracks API calls and simulated AI-token usage,
enforces subscription quotas, calculates usage cost, and integrates with
**Stripe test mode** for subscription management.

The implementation focuses on the correctness problems highlighted by
the FlyRank capstone brief: idempotent metering, quota boundaries,
token-category pricing, persistent billing state, and verified Stripe
webhooks.

> **Scope:** AI usage is simulated. No live AI model or AI API key is
> required.

------------------------------------------------------------------------

## Table of Contents

1.  [Features](#1-features)
2.  [Architecture](#2-architecture)
3.  [Technology Stack](#3-technology-stack)
4.  [Repository Structure](#4-repository-structure)
5.  [Database Design](#5-database-design)
6.  [Plans and Quotas](#6-plans-and-quotas)
7.  [API Reference](#7-api-reference)
8.  [Idempotency](#8-idempotency)
9.  [Cost Calculation](#9-cost-calculation)
10. [Stripe Test Mode](#10-stripe-test-mode)
11. [Environment Variables](#11-environment-variables)
12. [Local Setup](#12-local-setup)
13. [Quick Demo](#13-quick-demo)
14. [Testing](#14-testing)
15. [Evidence and Acceptance Checks](#15-evidence-and-acceptance-checks)
16. [Security](#16-security)
17. [Design Decisions](#17-design-decisions)
18. [Limitations](#18-limitations)
19. [Capstone Submission Pack](#19-capstone-submission-pack)
20. [Useful Commands](#20-useful-commands)
21. [Project Status](#21-project-status)
22. [License](#22-license)
23. [Final Checklist](#23-final-checklist)

------------------------------------------------------------------------

## 1. Features

-   Multi-tenant usage tracking
-   Exactly-once metering at the database idempotency boundary
-   API-call quota enforcement
-   AI-token quota enforcement
-   `429 Too Many Requests` for usage-limit violations
-   `402 Payment Required` for unavailable subscription states
-   Separate pricing for input, cached-input, output, and reasoning
    tokens
-   Integer micro-cent arithmetic to avoid floating-point currency
    calculations
-   PostgreSQL persistence through SQLAlchemy and Alembic
-   Stripe Checkout in test mode
-   Stripe webhook signature verification
-   Stripe webhook event-ID deduplication (replayed/duplicate
    deliveries are recorded and ignored, not reprocessed)
-   `customer.subscription.updated` status changes are synced to the
    local subscription row, not just logged
-   `/usage` rollups are scoped to the active subscription's current
    billing period, matching the window the quota check enforces
-   Automated tests for metering, quotas, subscription states, webhook
    replay protection, and usage rollups
-   Swagger/OpenAPI documentation through FastAPI

------------------------------------------------------------------------

## 2. Architecture

The service follows a small layered design: HTTP endpoints receive
requests, the metering service owns billing logic, and
SQLAlchemy/PostgreSQL provides persistence.

``` text
                           +----------------+
                           |     Client     |
                           +-------+--------+
                                   |
                    +--------------+--------------+
                    |                             |
                    v                             v
             POST /generate                  GET /usage
                    |                             |
                    v                             v
             +-------------+              +---------------+
             |  FastAPI    |              | Usage Rollup  |
             |  HTTP layer |              | + Cost Math   |
             +------+------+              +-------+-------+
                    |                             |
                    v                             |
             +-------------+                      |
             | Metering    |                      |
             | Service     |                      |
             +------+------+                      |
                    |                             |
                    +--------------+--------------+
                                   |
                                   v
                         +--------------------+
                         |    PostgreSQL      |
                         |                    |
                         | plans              |
                         | tenants            |
                         | subscriptions      |
                         | usage_events       |
                         +--------------------+

        Stripe Checkout
              |
              v
       +--------------+
       | Stripe Test  |
       |     Mode     |
       +------+-------+
              |
       signed webhook
              |
              v
     POST /webhooks/stripe
              |
              v
       +--------------+
       | Subscription |
       | persistence  |
       +--------------+
```

### Main modules

  -----------------------------------------------------------------------
  Module                              Responsibility
  ----------------------------------- -----------------------------------
  `app/main.py`                       FastAPI application, `/generate`,
                                      and `/usage`

  `app/services.py`                   Idempotency, subscription checks,
                                      quotas, usage recording

  `app/routers/stripe.py`             Stripe Checkout and webhook
                                      processing

  `app/models.py`                     SQLAlchemy models

  `app/schemas.py`                    Pydantic request schemas

  `app/database.py`                   Database engine/session
                                      configuration

  `app/config.py`                     Pricing constants

  `alembic/`                          Database migrations

  `seed.py`                           Demo data creation

  `tests/`                            Automated tests
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 3. Technology Stack

-   Python 3.11+
-   FastAPI
-   Uvicorn
-   SQLAlchemy
-   Alembic
-   PostgreSQL 15
-   Docker / Docker Compose
-   Stripe test mode
-   Stripe CLI
-   Pytest
-   Pydantic
-   psycopg2

The capstone brief explicitly supports Python + FastAPI, PostgreSQL
through Docker, Stripe test mode, Stripe CLI, and simulated AI usage.

------------------------------------------------------------------------

## 4. Repository Structure

The repository also includes the evaluator manifest `capstone.yaml`, the
AI/build log `BUILDLOG.md`, the evidence file `EVIDENCE.md`, and the Python
dependency manifest `requirements.txt`.

``` text
.
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── services.py
│   └── routers/
│       ├── __init__.py
│       └── stripe.py
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 2c91045ea080_initial_schema.py
├── docker/
│   └── init.sql
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_idempotency.py
│   ├── test_quota.py
│   └── test_stripe.py
├── seed.py
├── docker-compose.yml
├── alembic.ini
├── .env.example
├── requirements.txt
├── capstone.yaml
├── BUILDLOG.md
├── Database Design.pdf
├── EVIDENCE.md
├── LICENSE
└── README.md
```

------------------------------------------------------------------------

## 5. Database Design

The core schema contains the four entities required by the capstone:

``` text
plans
  |
  +----< subscriptions >---- tenants
                                |
                                +----< usage_events
```

### `plans`

Stores subscription tiers and their limits.

  Column               Description
  -------------------- -----------------------------
  `id`                 UUID primary key
  `name`               Plan name
  `api_call_limit`     Maximum API calls
  `ai_token_limit`     Maximum AI tokens
  `base_price_cents`   Monthly plan price in cents

### `tenants`

Represents customer organizations and provides the tenant boundary for
usage.

  Column                 Description
  ---------------------- ------------------------------------
  `id`                   UUID primary key
  `name`                 Tenant name
  `stripe_customer_id`   Optional Stripe customer reference
  `created_at`           Creation timestamp

### `subscriptions`

Associates a tenant with a plan and stores subscription/billing-period
state.

  Column                     Description
  -------------------------- -------------------------------
  `id`                       UUID primary key
  `tenant_id`                Foreign key to `tenants`
  `plan_id`                  Foreign key to `plans`
  `stripe_subscription_id`   Stripe subscription reference
  `status`                   Subscription status
  `current_period_start`     Billing period start
  `current_period_end`       Billing period end

### `usage_events`

An append-only ledger of billable activity.

  Column              Description
  ------------------- ---------------------------
  `id`                UUID primary key
  `tenant_id`         Foreign key to `tenants`
  `usage_type`        `api_call` or `ai_token`
  `quantity`          Usage quantity
  `idempotency_key`   Request deduplication key
  `metadata`          JSONB token breakdown
  `created_at`        Event timestamp

The database defines the idempotency boundary as:

``` text
UNIQUE (tenant_id, idempotency_key)
```

This prevents duplicate usage records for the same tenant and request
key.

------------------------------------------------------------------------

## 6. Plans and Quotas

The seeded/demo plans are:

| Plan | API Calls | AI Tokens | Monthly Price |
| :--- | ---: | ---: | ---: |
| Free | 1,000 | 100,000 | $0 |
| Pro | 10 | 50,000 | $20 |

The seeded Pro plan intentionally uses a low API-call limit and a 50,000-token
limit to make quota-boundary testing easy during local evaluation. The plan
price is stored as 2,000 cents.

The system checks current usage before accepting a billable action.

### API-call quota

If the requested API call would exceed the plan's API-call limit:

``` http
429 Too Many Requests
```

with a clear quota-exceeded message.

### AI-token quota

If the requested token quantity would exceed the plan's AI-token limit:

``` http
429 Too Many Requests
```

with a clear quota-exceeded message.

### Inactive subscriptions

The implementation rejects requests for unavailable subscription states
including:

``` text
past_due
canceled
unpaid
expired
incomplete
```

These requests return:

``` http
402 Payment Required
```

------------------------------------------------------------------------

## 7. API Reference

Local base URL:

``` text
http://127.0.0.1:8000
```

Interactive Swagger documentation:

``` text
http://127.0.0.1:8000/docs
```

OpenAPI schema:

``` text
http://127.0.0.1:8000/openapi.json
```

### `POST /generate`

Records one simulated billable generation.

#### Headers

The current implementation uses:

``` http
X-Tenant-Id: <tenant_uuid>
Idempotency-Key: <unique_key>
```

> Note: the current implementation does **not** implement bearer-token
> authentication. Tenant identification is performed with `X-Tenant-Id`.

#### Request

``` json
{
  "prompt": "Write a short story about a fox.",
  "simulated_usage": {
    "input_tokens": 100,
    "cached_input_tokens": 50,
    "output_tokens": 100,
    "reasoning_tokens": 50
  }
}
```

Total tokens in this example:

``` text
100 + 50 + 100 + 50 = 300
```

#### Success

The current implementation returns a successful result with a recorded
status, for example:

``` json
{
  "status": "recorded",
  "message": "Usage recorded successfully."
}
```

A retry using the same tenant and idempotency key is returned as a
deduplicated request instead of creating another usage record.

#### Error boundaries

  -----------------------------------------------------------------------
  Status                              Meaning
  ----------------------------------- -----------------------------------
  `400`                               Invalid/missing request context or
                                      no active subscription where
                                      applicable

  `402`                               Subscription/payment state does not
                                      permit usage

  `429`                               Usage quota would be exceeded
  -----------------------------------------------------------------------

### `GET /usage`

Returns the tenant usage summary and calculated cost.

Header:

``` http
X-Tenant-Id: <tenant_uuid>
```

Response shape:

``` json
{
  "used": {
    "api_calls": 1,
    "ai_tokens": 300
  },
  "limit": {
    "api_calls": 1000,
    "ai_tokens": 100000
  },
  "cost_cents": 8
}
```

### `POST /checkout`

Creates a Stripe Checkout subscription session for a tenant.

``` text
POST /checkout?tenant_id=<tenant_uuid>
```

Successful response:

``` json
{
  "checkout_url": "https://checkout.stripe.com/..."
}
```

An already-active tenant is blocked from creating another active
Checkout subscription through this endpoint.

### `POST /webhooks/stripe`

Receives Stripe events and verifies the Stripe signature before
processing them.

Supported event types in the current implementation:

``` text
checkout.session.completed
customer.subscription.updated
customer.subscription.deleted
```

Every incoming event's Stripe `id` is recorded in a `stripe_events`
table before it is handled. If the same event `id` is delivered again
(Stripe retry, `stripe trigger` replay, or a manual redelivery from the
Dashboard), the handler returns `{"status": "ignored_duplicate_event"}`
without reprocessing it.

`checkout.session.completed` updates the tenant's local subscription to
`active` and stores the Stripe subscription ID.

`customer.subscription.updated` syncs the tenant's local subscription
`status` to whatever status Stripe reports (e.g. `active`, `past_due`,
`unpaid`), so quota/subscription checks stay accurate between full
Checkout flows.

`customer.subscription.deleted` marks the matching local subscription as
`canceled`.

------------------------------------------------------------------------

## 8. Idempotency

Idempotency prevents network retries from becoming duplicate billable
actions.

The request supplies:

``` http
Idempotency-Key: <unique-key>
```

The database protects the key with:

``` text
(tenant_id, idempotency_key)
```

The metering flow is:

``` text
Request
   |
   v
Existing (tenant, key)?
   |
   +---- YES ----> return deduplicated result
   |
   +---- NO -----> subscription check
                     |
                     v
                  quota check
                     |
                     v
                 record usage
```

A successful `/generate` call records two ledger rows:

1.  one `api_call` event
2.  one `ai_token` event

The AI-token event stores the individual token categories in JSONB
metadata so that billing can price each category correctly.

------------------------------------------------------------------------

## 9. Cost Calculation

The application uses **integer micro-cents** rather than floating-point
arithmetic.

Configured constants in `app/config.py` are:

  Usage                                  Rate
  ---------------------- --------------------
  API call                 10,000 micro-cents
  Standard input token        100 micro-cents
  Cached input token           50 micro-cents
  Output token                400 micro-cents
  Reasoning token             400 micro-cents

The rules are:

-   cached input is cheaper than standard input
-   reasoning tokens are billed at the output rate
-   categories are priced separately rather than being summed first

### Example calculation

For one API call and:

``` json
{
  "input_tokens": 100,
  "cached_input_tokens": 50,
  "output_tokens": 100,
  "reasoning_tokens": 50
}
```

``` text
API call:       1 × 10,000 = 10,000 micro-cents
Input:        100 × 100   = 10,000 micro-cents
Cached input:  50 × 50    =  2,500 micro-cents
Output:       100 × 400   = 40,000 micro-cents
Reasoning:     50 × 400   = 20,000 micro-cents

Total = 82,500 micro-cents
      = 8 integer cents after conversion
```

The `/usage` endpoint applies the same category-by-category calculation
to persisted usage metadata.

------------------------------------------------------------------------

## 10. Stripe Test Mode

Stripe is used in **test mode only**. No real money is moved.

### Start the local webhook listener

From the repository directory:

``` powershell
.\stripe listen --forward-to localhost:8000/webhooks/stripe
```

Stripe CLI will print a webhook signing secret. Put that value in `.env`
as:

``` text
STRIPE_WEBHOOK_SECRET=whsec_...
```

Never commit the secret.

### Trigger a test event

``` powershell
.\stripe trigger checkout.session.completed
```

### End-to-end Checkout flow

1.  Start FastAPI.
2.  Start the Stripe CLI listener.
3.  Seed a tenant.
4.  Call `POST /checkout?tenant_id=<tenant_uuid>`.
5.  Open the returned Checkout URL.
6.  Complete the test Checkout using Stripe's test card
    `4242 4242 4242 4242`.
7.  Stripe sends `checkout.session.completed` to `/webhooks/stripe`.
8.  The local subscription is updated to `active`.
9.  Verify the subscription in PostgreSQL.

The live development run used Stripe CLI forwarding to:

``` text
http://localhost:8000/webhooks/stripe
```

and recorded successful HTTP `200` responses for Checkout webhook
delivery.

------------------------------------------------------------------------

## 11. Environment Variables

Create `.env` from `.env.example`.

The supplied `.env.example` contains safe placeholders:

``` env
DATABASE_URL="postgresql://user:password@localhost:5433/dbname"
STRIPE_SECRET_KEY="sk_test_placeholder"
STRIPE_WEBHOOK_SECRET="whsec_placeholder"
STRIPE_PRICE_ID="price_test_placeholder"
```

`STRIPE_PRICE_ID` must be a **test-mode** Price ID from your own Stripe
Dashboard (Products → your Pro product → pricing → copy the Price ID,
starts with `price_...`). This keeps the repo runnable by anyone who
clones it and configures their own Stripe test account, instead of
depending on a Price ID from the original author's account.

For the included Docker Compose database, replace the database placeholder
with:

``` env
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/metering_db
```

Then provide your own Stripe **test-mode** secret key and webhook signing
secret in `.env`. Never commit `.env`.

The supplied `.env.example` contains placeholders only.

### Secret hygiene

Never commit:

-   `.env`
-   `sk_test_...` Stripe secret keys
-   `whsec_...` webhook secrets
-   private database credentials

If a real secret is accidentally exposed, rotate it immediately.

------------------------------------------------------------------------

## 12. Local Setup

### Prerequisites

Install:

-   Python 3.11+
-   Docker Desktop
-   Stripe CLI

Verify:

``` powershell
python --version
docker --version
docker compose version
.\stripe --version
```

### 1. Clone

``` powershell
git clone <your-public-repository-url>
cd <your-repository-directory>
```

### 2. Create a virtual environment

Windows PowerShell:

``` powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

Install all project dependencies from `requirements.txt`:

```powershell
pip install -r requirements.txt
```

### 4. Start PostgreSQL

``` powershell
docker compose up -d
```

The Docker Compose configuration exposes PostgreSQL on host port `5433`
and creates:

``` text
metering_db
metering_test_db
```

### 5. Configure `.env`

``` powershell
Copy-Item .env.example .env
```

Set the local database URL to:

``` text
postgresql://postgres:postgres@localhost:5433/metering_db
```

and provide Stripe test credentials.

### 6. Run migrations

``` powershell
alembic upgrade head
```

### 7. Seed demo data

``` powershell
python seed.py
```

The command creates demo plans, a tenant, and an active subscription,
then prints the tenant UUID.

### 8. Start FastAPI

This is the single application run command listed in `capstone.yaml`:

``` powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at:

``` text
http://127.0.0.1:8000
```

------------------------------------------------------------------------

## 13. Quick Demo

After running `seed.py`, replace `<TENANT_ID>` with the printed tenant
UUID.

### Record usage

``` powershell
curl.exe -X POST "http://127.0.0.1:8000/generate" `
  -H "Content-Type: application/json" `
  -H "X-Tenant-Id: <TENANT_ID>" `
  -H "Idempotency-Key: demo-request-001" `
  -d "{\"prompt\":\"Write a short story about a fox.\",\"simulated_usage\":{\"input_tokens\":100,\"cached_input_tokens\":50,\"output_tokens\":100,\"reasoning_tokens\":50}}"
```

### Retry the same request

Run the same command again with the same:

``` text
X-Tenant-Id
Idempotency-Key
```

The retry should be reported as deduplicated and should not create
additional usage records.

### Read usage

``` powershell
curl.exe "http://127.0.0.1:8000/usage" `
  -H "X-Tenant-Id: <TENANT_ID>"
```

### Open Swagger

``` text
http://127.0.0.1:8000/docs
```

------------------------------------------------------------------------

## 14. Testing

Run the full automated suite with:

``` powershell
pytest -v
```

The suite was re-run after the post-submission hardening pass (webhook
replay dedup, subscription-status sync, usage-period scoping) and
completed with:

``` text
collected 15 items

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
tests/test_stripe.py::test_webhook_duplicate_event_id_is_ignored PASSED
tests/test_stripe.py::test_webhook_subscription_updated_syncs_status PASSED
tests/test_usage_rollup.py::test_usage_excludes_events_outside_current_billing_period PASSED

15 passed, 2 warnings in 4.51s
```

The two warnings are the same pre-existing `httpx`/Starlette
`TestClient` deprecation warnings noted below; they do not affect test
results.

The test suite covers:

### Idempotency

-   first request records usage
-   one API-call event is created
-   one AI-token event is created
-   token quantity is calculated correctly
-   duplicate request is deduplicated
-   duplicate request creates no additional usage events

### Quotas

-   API-call quota returns `429`
-   AI-token quota returns `429`
-   `past_due` returns `402`
-   `canceled` returns `402`
-   `unpaid` returns `402`
-   `expired` returns `402`
-   `incomplete` returns `402`

### Stripe

-   Checkout session creation succeeds
-   active tenants are prevented from creating another Checkout session
-   `checkout.session.completed` updates the local subscription
-   a duplicate delivery of the same event `id` is ignored and does not
    reprocess the event
-   `customer.subscription.updated` syncs its Stripe status onto the
    local subscription row

### Usage rollups

-   `/usage` excludes usage events recorded outside the active
    subscription's current billing period

The tests use a separate PostgreSQL test database:

``` text
localhost:5433/metering_test_db
```

------------------------------------------------------------------------

## 15. Evidence and Acceptance Checks

The capstone requires concrete proof in `EVIDENCE.md` rather than
unsupported claims.

The project's evidence document contains:

-   idempotency test output
-   API-call and AI-token quota evidence
-   inactive subscription evidence
-   pricing calculation
-   Stripe Checkout/webhook evidence
-   PostgreSQL subscription persistence
-   final Pytest output
-   FastAPI runtime evidence

Recorded final test result at the original submission draft:

``` text
12 passed, 2 warnings
```

Three additional tests were added in a later hardening pass (webhook
replay dedup, subscription-status sync, usage-period scoping) and the
full suite was re-run, completing with:

``` text
15 passed, 2 warnings in 4.51s
```

See Section 14 for the full per-test breakdown of the re-run.

Recorded live Stripe evidence includes successful forwarding of:

``` text
checkout.session.completed
```

to:

``` text
POST http://localhost:8000/webhooks/stripe
```

with HTTP `200`.

> Evidence should contain only safe identifiers. Never paste Stripe
> webhook secrets or private credentials into the repository.

------------------------------------------------------------------------

## 16. Security

This is a local/test-mode capstone service, not a production billing
platform.

### Tenant isolation

Usage records are associated with a tenant ID, and idempotency is
tenant-scoped:

``` text
tenant_id + idempotency_key
```

### Stripe verification

Webhook requests are verified using Stripe's signed raw request body
before event handling.

### Secrets

Secrets are loaded from environment variables and should never be
committed or logged.

### Production hardening

A production version would additionally require authenticated tenant
credentials, stronger authorization, secret management, monitoring, rate
limiting, and more robust Stripe event processing.

------------------------------------------------------------------------

## 17. Design Decisions

### PostgreSQL

PostgreSQL provides durable relational persistence and database-level
uniqueness constraints for the idempotency boundary.

### Append-only usage ledger

Individual usage events provide an auditable record of billable actions
and allow later aggregation into usage summaries.

### Integer micro-cents

Using integer micro-cents avoids floating-point errors while preserving
precision during token pricing.

### Simulated AI usage

The capstone is about metering and billing, not model inference.
Simulated token counts make the system deterministic, free, and easy to
test.

### Stripe test mode

The project needs realistic subscription and webhook behavior without
real payments, so Stripe test mode is sufficient.

------------------------------------------------------------------------

## 18. Limitations

This section is intentionally explicit. The README should not claim that
functionality exists when the current code does not implement it.

### Authentication

The API currently uses `X-Tenant-Id` rather than a real tenant API
key/bearer authentication mechanism.

**Status:** simplified capstone authentication boundary.

### Background jobs

The current project has no queue/worker/background-job subsystem.
Metering and webhook work is handled synchronously.

**Status:** not implemented.

### Dependency versions

The repository includes a `requirements.txt` file containing the Python
dependencies required by the application and test suite. The dependency
versions are currently unpinned.

Install them with:

``` powershell
pip install -r requirements.txt
```

**Status:** dependency manifest implemented; exact version pinning is
not currently used.

### Production billing features

The following are intentionally outside the core implementation:

-   real payments
-   invoices
-   proration
-   overage billing
-   production reconciliation jobs
-   customer-facing frontend
-   live AI model calls

------------------------------------------------------------------------

## 19. Capstone Submission Pack

The FlyRank brief specifies these required repository files:

  -----------------------------------------------------------------------
  File                                Purpose
  ----------------------------------- -----------------------------------
  `README.md`                         System description, architecture
                                      diagram, exact run/seed steps,
                                      limitations

  `capstone.yaml`                     Evaluator manifest containing run,
                                      seed, optional test, base URL, and
                                      probe endpoints

  `EVIDENCE.md`                       One concrete proof for each
                                      requirements checkbox

  `BUILDLOG.md`                       Honest AI-usage/build log

  `.env.example`                      Safe environment-variable
                                      placeholders

  `requirements.txt`                  Python dependency manifest
  -----------------------------------------------------------------------

Before submitting, verify that all required submission files are
committed to the public repository. The evaluator manifest in
`capstone.yaml` points to the same run command, seed command, test command,
base URL, and probe endpoints documented in this README.

------------------------------------------------------------------------

## 20. Useful Commands

Start PostgreSQL:

``` powershell
docker compose up -d
```

Stop PostgreSQL:

``` powershell
docker compose down
```

Run migrations:

``` powershell
alembic upgrade head
```

Seed demo data:

``` powershell
python seed.py
```

Start FastAPI:

``` powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run tests:

``` powershell
pytest -v
```

Start Stripe webhook forwarding:

``` powershell
.\stripe listen --forward-to localhost:8000/webhooks/stripe
```

Trigger a Stripe test event:

``` powershell
.\stripe trigger checkout.session.completed
```

------------------------------------------------------------------------

## 21. Project Status

The project has been exercised locally with:

-   PostgreSQL through Docker
-   FastAPI development server
-   automated Pytest tests
-   Stripe test mode
-   Stripe CLI webhook forwarding
-   PostgreSQL subscription verification

Recorded final automated result at the original submission draft:

``` text
12 passed, 2 warnings
```

Re-run after the post-submission hardening pass (webhook replay dedup,
subscription-status sync, usage-period scoping):

``` text
15 passed, 2 warnings in 4.51s
```

The FastAPI runtime was also observed successfully serving:

``` text
GET  /docs
GET  /openapi.json
POST /generate
GET  /usage
POST /checkout
POST /webhooks/stripe
```

------------------------------------------------------------------------

## 22. License

See [`LICENSE`](LICENSE).

------------------------------------------------------------------------

## 23. Final Checklist

Before submitting the public repository:

-   [ ] `README.md` is present
-   [ ] architecture diagram is present
-   [ ] clean-machine setup is documented
-   [ ] run command is documented
-   [ ] seed command is documented
-   [ ] API endpoints are documented
-   [ ] quota behavior is documented
-   [ ] pricing rules are documented
-   [ ] Stripe test-mode flow is documented
-   [ ] limitations are documented honestly
-   [ ] `EVIDENCE.md` is present with concrete proofs
-   [ ] `BUILDLOG.md` is present
-   [ ] `capstone.yaml` is present
-   [ ] `.env.example` is present
-   [ ] `requirements.txt` is present and installation is documented
-   [ ] `.env` is ignored and not committed
-   [ ] no Stripe secrets are committed
-   [ ] `pytest -v` passes
-   [ ] PostgreSQL starts with Docker Compose
-   [ ] migrations run successfully
-   [ ] `python seed.py` succeeds
-   [ ] FastAPI starts with the documented command
-   [ ] Stripe CLI forwards webhooks locally

------------------------------------------------------------------------

**FlyRank Internship --- Backend Track --- Usage Metering & Billing
Engine Capstone**