# BUILDLOG.md

# Build Log — Usage Metering & Billing Engine

## Overview

This project was developed as the FlyRank Backend Track Capstone: **Usage Metering & Billing Engine**.

The core backend implementation was done independently, with AI assistance used selectively for areas where I needed to learn or understand unfamiliar tooling and for final documentation/formatting.

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

## Honest Summary

The backend architecture, database layer, metering logic, routes, and pytest coverage were implemented by me.

I used **Gemini heavily for learning and troubleshooting the Stripe CLI/Dashboard side**, including the Stripe routes and tests.

I used **ChatGPT for structuring and polishing the README.md and EVIDENCE.md**, starting from project information, raw inputs, and actual evidence supplied by me.

AI therefore played an important supporting role, especially for Stripe and documentation, but the final project was reviewed, tested, and adapted against the actual implementation before submission.
