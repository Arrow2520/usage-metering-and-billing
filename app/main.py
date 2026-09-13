from fastapi import FastAPI, Depends, Header, HTTPException, status
from app.schemas import TokenUsage, GenerateRequest
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import check_quota_and_record_usage
from app.routers.stripe import router
from app.config import PRICING
from app.models import Subscription, Plan, UsageEvent

app = FastAPI(title="Usage Metering Engine")
app.include_router(router)

@app.post("/generate", status_code=status.HTTP_200_OK)
def generate_endpoint(
    payload: GenerateRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    total_tokens = (
        payload.simulated_usage.input_tokens
        + payload.simulated_usage.cached_input_tokens
        + payload.simulated_usage.output_tokens
        + payload.simulated_usage.reasoning_tokens
    )

    result = check_quota_and_record_usage(
        db=db,
        tenant_id=x_tenant_id,
        idempotency_key=idempotency_key,
        requested_api_calls=1,
        requested_tokens=total_tokens,
        token_breakdown=payload.simulated_usage.model_dump()
    )
    return result


@app.get("/usage", status_code=status.HTTP_200_OK)
def get_tenant_usage(
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    db: Session = Depends(get_db)
):
    # 1. Get the tenant's active plan limits
    sub = db.query(Subscription).filter(
        Subscription.tenant_id == x_tenant_id, 
        Subscription.status == "active"
    ).first()
    
    if not sub:
        raise HTTPException(status_code=400, detail="No active subscription found.")
        
    plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()

    # 2. Fetch all usage events for this tenant
    events = db.query(UsageEvent).filter(UsageEvent.tenant_id == x_tenant_id).all()

    # 3. Aggregate totals and cost
    total_api_calls = 0
    total_tokens = 0
    total_cost_micro_cents = 0

    for event in events:
        if event.usage_type == "api_call":
            total_api_calls += event.quantity
            total_cost_micro_cents += (event.quantity * PRICING["api_call"])
            
        elif event.usage_type == "ai_token":
            total_tokens += event.quantity
            
            # Fallback to empty dict if metadata is missing
            meta = event.event_metadata or {}
            
            # Calculate cost using the exact rules from the brief
            total_cost_micro_cents += (meta.get("input_tokens", 0) * PRICING["input_token"])
            total_cost_micro_cents += (meta.get("cached_input_tokens", 0) * PRICING["cached_input_token"])
            total_cost_micro_cents += (meta.get("output_tokens", 0) * PRICING["output_token"])
            total_cost_micro_cents += (meta.get("reasoning_tokens", 0) * PRICING["reasoning_token"])

    # Convert micro-cents to standard cents for the final output
    total_cost_cents = total_cost_micro_cents // 10000

    return {
        "used": {
            "api_calls": total_api_calls,
            "ai_tokens": total_tokens
        },
        "limit": {
            "api_calls": plan.api_call_limit,
            "ai_tokens": plan.ai_token_limit
        },
        "cost_cents": total_cost_cents
    }