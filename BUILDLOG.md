# BUILDLOG.md

# Build Log — Usage Metering & Billing Engine

## Overview

This project was developed as the FlyRank Backend Track Capstone: **Usage Metering & Billing Engine**.

The core backend implementation was done independently, with AI assistance used selectively: Gemini for learning the Stripe CLI/Dashboard workflow, ChatGPT for structuring the submission documentation, and Claude for a later review-and-fix pass on the finished implementation (see "Post-Submission Hardening Pass" below). Each tool's role is described separately rather than lumped together, since they were used differently.

## What I Built Myself

I implemented the main backend system myself, including:

- FastAPI application structure and backend setup.
- API routes and request/response handling.
- Database schema and SQLAlchemy models.
- PostgreSQL integration and database migrations.
- Usage metering logic.
- Idempotency handling for usage requests.
- Quota enforcement.
- Usage aggregation and cost calculation.
- Subscription and tenant handling.
- Pytest test cases for the backend endpoints and core requirements.
- Seed data and the local development workflow.
- Integration of the different backend components into the final working application.

The main goal was to understand and implement the backend architecture rather than simply generate a complete project with AI.

## Where AI Helped

### Stripe CLI and Stripe Dashboard

The main area where I relied on AI assistance was the Stripe portion of the project.

I used **Gemini** particularly to help me understand and work through:

- Stripe test-mode setup.
- Stripe Dashboard configuration.
- Stripe CLI installation and usage.
- Creating and testing Stripe Checkout flows.
- Forwarding Stripe webhook events to the local FastAPI server.
- Understanding Stripe webhook payloads and signatures.
- Implementing the Stripe-related routes.
- Writing and debugging Stripe-related tests.
- Troubleshooting issues encountered while connecting the local backend to Stripe.

I used this assistance as a learning aid. I did not treat the generated implementation as something to blindly copy; I worked through the Stripe flow, tested it locally, and used the process to understand how Stripe Checkout and webhooks fit into the backend.

This was also the part of the project where I learned the most from AI because Stripe CLI and Dashboard workflows were less familiar to me than the FastAPI/database side.

## Documentation Assistance

For the final submission documentation, I used **ChatGPT** to help turn my raw project information and evidence into structured submission documents.

### README.md

I provided the project details, implementation information, commands, and other raw inputs from my side. ChatGPT helped with:

- Organizing the README into clear sections.
- Structuring the architecture explanation.
- Formatting setup and run instructions.
- Presenting API endpoints and design decisions clearly.
- Making the documentation submission-ready.

The technical content was based on the actual project; the AI assistance was mainly used for organization, wording, and formatting.

### EVIDENCE.md

Similarly, I supplied the relevant test results, logs, and implementation evidence. ChatGPT helped me:

- Organize the evidence according to the capstone requirements.
- Map evidence to the corresponding requirements.
- Format test outputs and transcripts clearly.
- Make the document easier for an evaluator to verify.

I intentionally kept the evidence grounded in actual test runs and logs rather than inventing proof for functionality that was not tested.

## What AI Got Wrong / What I Changed

AI assistance was not always correct on the first attempt.

There were cases where generated suggestions did not exactly match my repository's implementation, particularly around:

- Stripe test setup and integration details.
- Documentation wording that initially described API behavior differently from the actual implementation.
- Some assumptions about project files and dependency configuration.

I reviewed these suggestions against the actual code, ran the application/tests, and changed the implementation or documentation where necessary.

One example was the Stripe testing workflow: an initial test implementation had an incompatibility with the mocked Stripe session object (`.to_dict()` behavior). I identified the failure from the test output and corrected the test/mock behavior before the final test run.

I also corrected documentation so that it reflects the actual API authentication/header behavior and actual pricing configuration instead of retaining older or assumed values.

## Learning Outcome

The project reinforced my understanding of:

- Designing a backend service with FastAPI.
- Modeling relational data with PostgreSQL and SQLAlchemy.
- Database migrations with Alembic.
- Idempotent API design.
- Quota and usage enforcement.
- Deterministic money/cost calculations.
- Stripe Checkout and webhook workflows.
- Webhook signature verification.
- Writing endpoint and integration tests.
- Using AI as a debugging and learning tool rather than as a replacement for understanding the implementation.

## Post-Submission Hardening Pass (Claude)

After drafting the initial README/EVIDENCE, I asked **Claude (Anthropic)**
to review the finished repository against the capstone's Section 6
requirements rather than just my own read of it. Claude read through
`app/main.py`, `app/services.py`, `app/routers/stripe.py`, `app/models.py`,
and the docs, and flagged four concrete gaps — three of which I had
already named honestly in the original Limitations section but not yet
fixed, plus one I hadn't caught:

1. **Stripe webhook replay deduplication was missing.** Events were
   signature-verified but never deduplicated by event ID, so a Stripe
   retry or a manual redelivery would be reprocessed instead of ignored —
   a requirement explicitly called out in the brief and tested by Probe 4.
2. **`customer.subscription.updated` was logged but never persisted**, so
   my local subscription status could silently drift from Stripe's real
   status (e.g. a plan going `past_due`).
3. **`/usage` wasn't scoped to the billing period.** It summed every usage
   event ever recorded for a tenant, while the quota check in
   `services.py` already scoped to `current_period_start`/
   `current_period_end` — an inconsistency between the two code paths.
4. **The Stripe Checkout Price ID was hardcoded** to a Price ID from my
   own Stripe test account (`price_1UFHPuH4OiqotMa2FJnXCjNN`), which
   would break for anyone cloning the repo and running it against their
   own account — violating the "a stranger can run it" submission rule.

**What Claude actually wrote:**
- A new `StripeEvent` model + Alembic migration (`stripe_events` table)
  keyed on Stripe's event `id`, and a check-and-insert block in the
  webhook handler that returns `{"status": "ignored_duplicate_event"}`
  on a replayed event ID instead of reprocessing it.
- A DB write inside the `customer.subscription.updated` branch that syncs
  the Stripe-reported status onto the matching local `Subscription` row.
- A period filter added to the `/usage` query in `app/main.py`, matching
  the same window already used in `services.py`.
- Replaced the hardcoded Price ID with `STRIPE_PRICE_ID` read from the
  environment, added it to `.env.example`, and added a 500 guard if it's
  unset.
- Pinned `requirements.txt` to specific versions instead of leaving it
  unpinned.
- Three new tests covering the above:
  `tests/test_stripe.py::test_webhook_duplicate_event_id_is_ignored`,
  `tests/test_stripe.py::test_webhook_subscription_updated_syncs_status`,
  and `tests/test_usage_rollup.py::test_usage_excludes_events_outside_current_billing_period`,
  written to match the existing fixture/mocking patterns in
  `tests/conftest.py`.

**What I did, not Claude:** I reviewed every diff against my own
understanding of the schema and request flow before accepting it — in
particular checking that the webhook dedup check only skips *processing*
and still returns `200` (so Stripe doesn't keep retrying a legitimately
handled event), and that the new `/usage` filter didn't change behavior
for the existing idempotency/quota tests. I re-ran `pytest -v` against my
live PostgreSQL test database after these changes and got **15 passed, 2
warnings** — all three new tests passed and none of the original 12
regressed. That output is recorded in `EVIDENCE.md` Section 7a.

**Where I'd push back if evaluating this myself:** Claude's fixes were
scoped tightly to the four gaps identified — it didn't refactor unrelated
code, and it kept the existing code style (e.g. `print()` logging in the
webhook handler) rather than introducing something inconsistent with the
rest of the file. I asked it to explain each change before accepting it,
which is the same standard I'd apply to a code review from a person.

## Honest Summary

The backend architecture, database layer, metering logic, routes, and pytest coverage were implemented by me.

I used **Gemini heavily for learning and troubleshooting the Stripe CLI/Dashboard side**, including the Stripe routes and tests.

I used **ChatGPT for structuring and polishing the README.md and EVIDENCE.md**, starting from project information, raw inputs, and actual evidence supplied by me.

I used **Claude for a pre-submission review and hardening pass**: it read the finished repo against the capstone brief, found four real gaps (webhook replay dedup, `subscription.updated` not persisting, `/usage` not period-scoped, a hardcoded Stripe Price ID), and wrote the code and tests to fix them, which I reviewed before accepting. This is a different kind of AI involvement than the other two — Gemini and ChatGPT helped me learn and document *my own* implementation, while Claude authored specific fixes directly. I'm naming that distinction explicitly rather than blurring it into the same "AI helped" bucket.

AI therefore played an important supporting role throughout — learning aid, documentation polish, and a code-level review/fix pass — but every change was reviewed, tested where possible, and adapted against the actual implementation before submission.