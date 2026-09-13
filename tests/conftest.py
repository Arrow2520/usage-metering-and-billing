import pytest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.models import Base, Plan, Tenant, Subscription
from app.database import get_db
from app.main import app


# Separate PostgreSQL database used ONLY for tests.
TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5433/metering_test_db"


engine = create_engine(TEST_DATABASE_URL)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


@pytest.fixture
def db():
    """
    Create a fresh database schema for each test.
    """

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    """
    FastAPI test client using the test database.
    """

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def active_tenant(db):
    """
    Create a tenant with an active Free subscription.

    Current Free-plan limits:
        API calls  = 1000
        AI tokens  = 100000
    """

    plan = Plan(
        name="Free",
        api_call_limit=1000,
        ai_token_limit=100000,
        base_price_cents=0
    )

    tenant = Tenant(
        name="Pytest Tenant"
    )

    db.add(plan)
    db.add(tenant)
    db.commit()

    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status="active",
        current_period_start=datetime(2026, 1, 1),
        current_period_end=datetime(2027, 1, 1)
    )

    db.add(subscription)
    db.commit()

    return tenant


@pytest.fixture
def generate_payload():
    """
    Payload matching the current GenerateRequest schema.
    """

    return {
        "prompt": "Write a short story about a fox.",
        "simulated_usage": {
            "input_tokens": 100,
            "cached_input_tokens": 50,
            "output_tokens": 100,
            "reasoning_tokens": 50
        }
    }