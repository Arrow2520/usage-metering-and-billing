import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Plan(Base):
    __tablename__ = "plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    api_call_limit = Column(Integer, nullable=False)
    ai_token_limit = Column(Integer, nullable=False)
    base_price_cents = Column(Integer, nullable=False)

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    stripe_subscription_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")  # active, past_due, canceled
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)

    plan = relationship("Plan")

class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    usage_type = Column(String, nullable=False)  # 'api_call' or 'ai_token'
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False)
    event_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency"),
    )

class StripeEvent(Base):
    """
    Records every processed Stripe webhook event ID so replayed/duplicate
    deliveries (Stripe retries, `stripe trigger` replays, etc.) are
    recognized and skipped instead of being reprocessed.
    """
    __tablename__ = "stripe_events"
    id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)