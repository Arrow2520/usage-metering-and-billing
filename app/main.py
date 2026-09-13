from fastapi import FastAPI, Depends, Header, HTTPException, status
from app.schemas import TokenUsage, GenerateRequest
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import check_quota_and_record_usage

app = FastAPI(title="Usage Metering Engine")

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