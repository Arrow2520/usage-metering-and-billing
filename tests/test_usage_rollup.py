from datetime import datetime
from app.models import UsageEvent


def test_usage_excludes_events_outside_current_billing_period(
    client,
    db,
    active_tenant
):
    """
    /usage must only sum events inside the active subscription's
    [current_period_start, current_period_end] window - the same window
    the quota check in services.py enforces against. A usage event
    recorded before the current period started (e.g. from a prior
    billing cycle) must not inflate the current period's totals.
    """
    # This event is BEFORE the active_tenant fixture's period
    # (2026-01-01 -> 2027-01-01), so it belongs to a past cycle.
    db.add(
        UsageEvent(
            tenant_id=active_tenant.id,
            usage_type="api_call",
            quantity=500,
            idempotency_key="stale-previous-period-call",
            event_metadata=None,
            created_at=datetime(2025, 6, 1)
        )
    )

    # This event IS inside the current period and must be counted.
    db.add(
        UsageEvent(
            tenant_id=active_tenant.id,
            usage_type="api_call",
            quantity=3,
            idempotency_key="current-period-call",
            event_metadata=None,
            created_at=datetime(2026, 2, 1)
        )
    )
    db.commit()

    response = client.get(
        "/usage",
        headers={"X-Tenant-Id": str(active_tenant.id)}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["used"]["api_calls"] == 3
