from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from app.models import Subscription, UsageEvent

def check_quota_and_record_usage(
    db: Session,
    tenant_id: str,
    idempotency_key: str,
    requested_api_calls: int,
    requested_tokens: int,
    token_breakdown: dict
) -> dict:
    # 1. Deduplication check: return previous result if already processed
    existing_event = db.query(UsageEvent).filter(
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.idempotency_key == idempotency_key
    ).first()
    if existing_event:
        return {"status": "deduplicated", "message": "Request previously recorded"}

    # 2. Subscription status check
    sub = db.query(Subscription).filter(
        Subscription.tenant_id == tenant_id
    ).order_by(Subscription.current_period_end.desc()).first()

    if not sub or sub.status in ["past_due", "canceled", "unpaid", "expired", "incomplete"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required. Plan is past due or expired."
        )

    # 3. Aggregate current usage within billing period
    now = datetime.utcnow()
    used_api_calls = db.query(func.coalesce(func.sum(UsageEvent.quantity), 0)).filter(
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.usage_type == "api_call",
        UsageEvent.created_at >= sub.current_period_start,
        UsageEvent.created_at <= sub.current_period_end
    ).scalar()

    used_tokens = db.query(func.coalesce(func.sum(UsageEvent.quantity), 0)).filter(
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.usage_type == "ai_token",
        UsageEvent.created_at >= sub.current_period_start,
        UsageEvent.created_at <= sub.current_period_end
    ).scalar()

    # 4. Boundary quota enforcement
    if (used_api_calls + requested_api_calls) > sub.plan.api_call_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"API call quota exceeded: {used_api_calls}/{sub.plan.api_call_limit}"
        )

    if (used_tokens + requested_tokens) > sub.plan.ai_token_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"AI token quota exceeded: {used_tokens}/{sub.plan.ai_token_limit}"
        )

    # 5. Atomic persistence with unique constraint protection
    try:
        call_event = UsageEvent(
            tenant_id=tenant_id,
            usage_type="api_call",
            quantity=requested_api_calls,
            idempotency_key=idempotency_key,
            event_metadata=None
        )
        token_event = UsageEvent(
            tenant_id=tenant_id,
            usage_type="ai_token",
            quantity=requested_tokens,
            idempotency_key=f"{idempotency_key}-tokens",
            event_metadata=token_breakdown
        )
        db.add_all([call_event, token_event])
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "deduplicated", "message": "Request previously recorded"}

    return {"status": "recorded", "used_calls": used_api_calls + requested_api_calls}