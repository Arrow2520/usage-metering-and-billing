from app.models import UsageEvent


def test_first_request_records_usage(
    client,
    db,
    active_tenant,
    generate_payload
):
    response = client.post(
        "/generate",
        headers={
            "X-Tenant-Id": str(active_tenant.id),
            "Idempotency-Key": "pytest-idempotency-001"
        },
        json=generate_payload
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "recorded"

    # One API-call event + one AI-token event
    events = db.query(UsageEvent).all()

    assert len(events) == 2

    api_event = db.query(UsageEvent).filter(
        UsageEvent.usage_type == "api_call"
    ).first()

    token_event = db.query(UsageEvent).filter(
        UsageEvent.usage_type == "ai_token"
    ).first()

    assert api_event is not None
    assert token_event is not None

    assert api_event.quantity == 1

    # 100 + 50 + 100 + 50 = 300
    assert token_event.quantity == 300

def test_duplicate_request_is_deduplicated(
    client,
    db,
    active_tenant,
    generate_payload
):
    headers = {
        "X-Tenant-Id": str(active_tenant.id),
        "Idempotency-Key": "pytest-duplicate-001"
    }

    # First request
    response_1 = client.post(
        "/generate",
        headers=headers,
        json=generate_payload
    )

    assert response_1.status_code == 200
    assert response_1.json()["status"] == "recorded"

    events_after_first_request = db.query(UsageEvent).count()

    assert events_after_first_request == 2

    # Same request again
    response_2 = client.post(
        "/generate",
        headers=headers,
        json=generate_payload
    )

    assert response_2.status_code == 200
    assert response_2.json()["status"] == "deduplicated"

    # No additional events should have been created.
    events_after_duplicate = db.query(UsageEvent).count()

    assert events_after_duplicate == 2