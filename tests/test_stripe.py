from unittest.mock import patch, MagicMock
from app.models import Subscription


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