from unittest.mock import patch, MagicMock
from app.models import Subscription, StripeEvent


@patch("app.routers.stripe.stripe.checkout.Session.create")
def test_create_checkout_session_success(mock_stripe_create, client, db, active_tenant):
    sub = db.query(Subscription).filter(Subscription.tenant_id == active_tenant.id).first()
    sub.status = "canceled"
    db.commit()

    class MockSession:
        url = "https://checkout.stripe.com/fake-test-url"
    
    mock_stripe_create.return_value = MockSession()

    response = client.post(f"/checkout?tenant_id={active_tenant.id}")

    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://checkout.stripe.com/fake-test-url"}
    mock_stripe_create.assert_called_once()


def test_create_checkout_session_blocked_for_active_tenant(client, active_tenant):
    response = client.post(f"/checkout?tenant_id={active_tenant.id}")
    
    assert response.status_code == 400
    assert "active subscription" in response.json()["detail"]


@patch("app.routers.stripe.stripe.Webhook.construct_event")
def test_webhook_checkout_completed_updates_db(mock_construct_event, client, db, active_tenant):
    sub = db.query(Subscription).filter(Subscription.tenant_id == active_tenant.id).first()
    sub.status = "past_due"
    db.commit()

    # Create a mock Stripe object that responds to .to_dict()
    mock_stripe_obj = MagicMock()
    mock_stripe_obj.to_dict.return_value = {
        "client_reference_id": str(active_tenant.id),
        "subscription": "sub_fake123"
    }

    mock_construct_event.return_value = {
        "type": "checkout.session.completed",
        "data": {
            "object": mock_stripe_obj
        }
    }

    headers = {"Stripe-Signature": "dummy_signature"}
    payload = {"dummy": "data"}

    response = client.post("/webhooks/stripe", json=payload, headers=headers)

    assert response.status_code == 200

    db.refresh(sub)
    assert sub.status == "active"
    assert sub.stripe_subscription_id == "sub_fake123"


@patch("app.routers.stripe.stripe.Webhook.construct_event")
def test_webhook_duplicate_event_id_is_ignored(mock_construct_event, client, db, active_tenant):
    sub = db.query(Subscription).filter(Subscription.tenant_id == active_tenant.id).first()
    sub.status = "past_due"
    db.commit()

    mock_stripe_obj = MagicMock()
    mock_stripe_obj.to_dict.return_value = {
        "client_reference_id": str(active_tenant.id),
        "subscription": "sub_fake456",
    }

    mock_construct_event.return_value = {
        "id": "evt_replayed_once",
        "type": "checkout.session.completed",
        "data": {
            "object": mock_stripe_obj
        },
    }

    headers = {"Stripe-Signature": "dummy_signature"}
    payload = {"dummy": "data"}

    # First delivery: processed normally, tenant upgraded to active.
    first = client.post("/webhooks/stripe", json=payload, headers=headers)
    assert first.status_code == 200
    db.refresh(sub)
    assert sub.status == "active"

    # Simulate a delivery retry / manual replay of the exact same event ID.
    sub.status = "past_due"
    db.commit()

    second = client.post("/webhooks/stripe", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json() == {"status": "ignored_duplicate_event"}

    # The replay must NOT reprocess the event, so status stays untouched.
    db.refresh(sub)
    assert sub.status == "past_due"

    # Exactly one StripeEvent row recorded for this event ID.
    assert db.query(StripeEvent).filter(StripeEvent.id == "evt_replayed_once").count() == 1


@patch("app.routers.stripe.stripe.Webhook.construct_event")
def test_webhook_subscription_updated_syncs_status(mock_construct_event, client, db, active_tenant):
    sub = db.query(Subscription).filter(Subscription.tenant_id == active_tenant.id).first()
    sub.stripe_subscription_id = "sub_sync789"
    sub.status = "active"
    db.commit()

    mock_stripe_obj = MagicMock()
    mock_stripe_obj.to_dict.return_value = {
        "id": "sub_sync789",
        "status": "past_due",
    }

    mock_construct_event.return_value = {
        "id": "evt_sub_updated_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": mock_stripe_obj
        },
    }

    headers = {"Stripe-Signature": "dummy_signature"}
    response = client.post("/webhooks/stripe", json={"dummy": "data"}, headers=headers)

    assert response.status_code == 200
    db.refresh(sub)
    assert sub.status == "past_due"