import os
import stripe
from fastapi import APIRouter, Request, HTTPException, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Subscription, StripeEvent

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")

@router.post("/checkout")
async def create_checkout_session(tenant_id: str, db: Session = Depends(get_db)):
    existing_sub = db.query(Subscription).filter(
        Subscription.tenant_id == tenant_id,
        Subscription.status == "active"
    ).first()

    if existing_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant already has an active subscription."
        )

    if not STRIPE_PRICE_ID:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_PRICE_ID is not configured. Set it in .env to a test-mode Price ID."
        )

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            # Stripe passes this back to us in the webhook
            client_reference_id=tenant_id, 
            success_url="http://localhost:8000/docs",
            cancel_url="http://localhost:8000/docs",
        )
        return {"checkout_url": checkout_session.url}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # 1. Get the raw body and signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    # 2. Verify the cryptographic signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    # 3. Replay / duplicate-delivery protection.
    # Stripe may deliver the same event more than once (retries, manual
    # replays via `stripe trigger` or the Dashboard). We record every
    # event ID we've processed and skip anything we've already handled.
    event_id = event.get('id') if isinstance(event, dict) else getattr(event, 'id', None)
    if event_id:
        try:
            db.add(StripeEvent(id=event_id, event_type=event['type']))
            db.commit()
        except IntegrityError:
            # Already processed this exact event ID - ignore the replay.
            db.rollback()
            return {"status": "ignored_duplicate_event"}

    # 4. Handle specific event types
    event_type = event['type']
    
    if event_type == 'checkout.session.completed':
        session = event['data']['object'].to_dict()
        
        # client_reference_id is our local tenant_id
        tenant_id = session.get('client_reference_id') 
        stripe_sub_id = session.get('subscription')
        
        print(f"Checkout completed! Tenant: {tenant_id}")
        
        if tenant_id:
            # Update the database
            db_sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
            if db_sub:
                db_sub.status = "active"
                db_sub.stripe_subscription_id = stripe_sub_id
                db.commit()
                print(f"Upgraded Tenant {tenant_id} to active status!")

    elif event_type == 'customer.subscription.updated':
        subscription = event['data']['object'].to_dict()
        stripe_status = subscription.get('status')
        sub_id = subscription.get('id')
        
        print(f"Subscription updated! ID: {sub_id} | New Status: {stripe_status}")

        # Mirror Stripe's status onto the local row so states like
        # past_due, unpaid, or a plan resume are reflected locally instead
        # of only being logged.
        if sub_id and stripe_status:
            db_sub = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == sub_id
            ).first()
            if db_sub:
                db_sub.status = stripe_status
                db.commit()
                print(f"Subscription {sub_id} status synced to '{stripe_status}' in database.")

    elif event_type == 'customer.subscription.deleted':
        subscription = event['data']['object'].to_dict()
        sub_id = subscription.get('id')
        
        print(f"Subscription canceled! ID: {sub_id}")
        
        # 1. Find the subscription by its Stripe ID
        db_sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == sub_id).first()
        
        # 2. Mark it as canceled
        if db_sub:
            db_sub.status = "canceled"
            db.commit()
            print(f"Subscription {sub_id} marked as canceled in database.")

    return {"status": "success"}