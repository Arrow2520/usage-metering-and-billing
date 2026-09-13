from app.models import UsageEvent, Subscription
import pytest


def test_api_call_quota_returns_429(
    client,
    db,
    active_tenant,
    generate_payload
):
    # Existing usage = exactly 1000 API calls
    for i in range(1000):
        db.add(
            UsageEvent(
                tenant_id=active_tenant.id,
                usage_type="api_call",
                quantity=1,
                idempotency_key=f"existing-api-{i}",
                event_metadata=None
            )
        )

    db.commit()

    response = client.post(
        "/generate",
        headers={
            "X-Tenant-Id": str(active_tenant.id),
            "Idempotency-Key": "pytest-api-quota-001"
        },
        json=generate_payload
    )

    assert response.status_code == 429

    data = response.json()

    assert "API call quota exceeded" in data["detail"]

def test_ai_token_quota_returns_429(
    client,
    db,
    active_tenant
):
    # Existing token usage = exactly 100000
    db.add(
        UsageEvent(
            tenant_id=active_tenant.id,
            usage_type="ai_token",
            quantity=100000,
            idempotency_key="existing-token-usage",
            event_metadata=None
        )
    )

    db.commit()

    payload = {
        "prompt": "Test token quota",
        "simulated_usage": {
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0
        }
    }

    response = client.post(
        "/generate",
        headers={
            "X-Tenant-Id": str(active_tenant.id),
            "Idempotency-Key": "pytest-token-quota-001"
        },
        json=payload
    )

    assert response.status_code == 429

    data = response.json()

    assert "AI token quota exceeded" in data["detail"]

@pytest.mark.parametrize(
    "subscription_status",
    [
        "past_due",
        "canceled",
        "unpaid",
        "expired",
        "incomplete"
    ]
)
def test_inactive_subscription_returns_402(
    client,
    db,
    active_tenant,
    generate_payload,
    subscription_status
):
    subscription = db.query(Subscription).filter(
        Subscription.tenant_id == active_tenant.id
    ).first()

    subscription.status = subscription_status

    db.commit()

    response = client.post(
        "/generate",
        headers={
            "X-Tenant-Id": str(active_tenant.id),
            "Idempotency-Key": f"pytest-status-{subscription_status}"
        },
        json=generate_payload
    )

    assert response.status_code == 402

    data = response.json()

    assert "Active subscription required" in data["detail"]