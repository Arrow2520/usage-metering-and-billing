from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import Plan, Tenant, Subscription

def seed_db():
    db = SessionLocal()
    
    # 1. Create a Pro Plan
    pro_plan = Plan(
        name="Pro",
        api_call_limit=10,       # Kept artificially low for easy 429 testing!
        ai_token_limit=50000,
        base_price_cents=2000
    )
    db.add(pro_plan)
    db.commit()

    # 2. Create a Test Tenant
    test_tenant = Tenant(name="Acme Corp Test")
    db.add(test_tenant)
    db.commit()

    # 3. Create an Active Subscription
    sub = Subscription(
        tenant_id=test_tenant.id,
        plan_id=pro_plan.id,
        status="active",
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30)
    )
    db.add(sub)
    db.commit()

    print(f"\nSeed successful!")
    print(f"Copy this Tenant ID for your tests: {test_tenant.id}\n")
    db.close()

if __name__ == "__main__":
    seed_db()