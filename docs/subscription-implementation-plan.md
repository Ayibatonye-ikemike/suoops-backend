# SuoPay: Subscription Model & Premium Features Implementation Plan

## Current State Analysis ✅

### What's Already Built:
1. ✅ **Payroll System** (Database + Backend)
   - `Worker` model with daily rates
   - `PayrollRun` and `PayrollRecord` models
   - `PayrollService` with worker management and payroll runs
   - `/payroll/workers` and `/payroll/runs` API endpoints
   - Tests in `tests/test_payroll.py`

2. ✅ **Invoice System** (Complete)
   - Full invoice creation, payment, and notifications
   - WhatsApp integration
   - PDF generation
   - Payment webhook handling

3. ✅ **Authentication** (Basic)
   - User model with JWT tokens
   - Login/Register endpoints

### What's Missing ❌:
1. ❌ **Subscription System** (Not implemented)
   - No subscription plans (Free, Pro, Enterprise)
   - No billing/payment for subscriptions
   - No feature gating based on plan
   - No subscription status tracking

2. ❌ **Branding/Logo Features** (Not implemented)
   - No logo_url field in User model
   - No branding fields (business name, colors, etc.)
   - No premium feature restrictions

3. ❌ **Payroll Frontend** (Not implemented)
   - Backend exists but no UI
   - No payroll dashboard
   - No payslip generation UI

---

## 🎯 Subscription Model Design

### Pricing Tiers

| Feature | **Free** | **Pro** (₦5,000/mo) | **Enterprise** (₦20,000/mo) |
|---------|----------|---------------------|------------------------------|
| **Invoices/month** | 10 | Unlimited | Unlimited |
| **Payment Processing** | ✅ Yes | ✅ Yes | ✅ Yes |
| **WhatsApp Notifications** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Custom Branding** | ❌ No | ✅ Logo + Colors | ✅ Full Branding |
| **Payroll System** | ❌ No | ✅ Up to 10 workers | ✅ Unlimited workers |
| **Payment Reminders** | ❌ No | ✅ Yes | ✅ Yes |
| **Analytics Dashboard** | ❌ Basic | ✅ Advanced | ✅ Advanced + Export |
| **API Access** | ❌ No | ❌ No | ✅ Yes |
| **Priority Support** | ❌ No | ❌ No | ✅ Yes |
| **Multi-user Accounts** | ❌ No | ❌ No | ✅ Yes |

### Subscription Status Flow
```
Free Trial (14 days) → Choose Plan → Active Subscription
                    ↓
              Expired/Cancelled → Downgrade to Free
```

---

## 📋 Implementation Plan

### Phase 1: Subscription Infrastructure (Week 1)

#### 1.1 Database Schema
```python
# Migration: 0006_add_subscriptions.py

# Add subscription plans
op.create_table(
    'subscription_plan',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('name', sa.String(50), nullable=False),  # Free, Pro, Enterprise
    sa.Column('price', sa.Numeric(scale=2), nullable=False),
    sa.Column('billing_period', sa.String(20), default='monthly'),  # monthly, yearly
    sa.Column('max_invoices', sa.Integer()),  # NULL = unlimited
    sa.Column('max_workers', sa.Integer()),  # NULL = unlimited
    sa.Column('has_branding', sa.Boolean(), default=False),
    sa.Column('has_payroll', sa.Boolean(), default=False),
    sa.Column('has_reminders', sa.Boolean(), default=False),
    sa.Column('has_analytics', sa.Boolean(), default=False),
    sa.Column('has_api_access', sa.Boolean(), default=False),
    sa.Column('active', sa.Boolean(), default=True),
)

# Add user subscription tracking
op.add_column('user', sa.Column('subscription_plan_id', sa.Integer(), 
              sa.ForeignKey('subscription_plan.id')))
op.add_column('user', sa.Column('subscription_status', sa.String(20), 
              default='trial'))  # trial, active, expired, cancelled
op.add_column('user', sa.Column('subscription_started_at', sa.DateTime(timezone=True)))
op.add_column('user', sa.Column('subscription_expires_at', sa.DateTime(timezone=True)))
op.add_column('user', sa.Column('trial_expires_at', sa.DateTime(timezone=True)))

# Add usage tracking
op.add_column('user', sa.Column('invoices_this_month', sa.Integer(), default=0))
op.add_column('user', sa.Column('last_invoice_reset', sa.DateTime(timezone=True)))

# Add branding fields (for Pro and Enterprise)
op.add_column('user', sa.Column('business_name', sa.String(200)))
op.add_column('user', sa.Column('business_email', sa.String(120)))
op.add_column('user', sa.Column('business_phone', sa.String(32)))
op.add_column('user', sa.Column('business_address', sa.Text()))
op.add_column('user', sa.Column('logo_url', sa.String(500)))
op.add_column('user', sa.Column('brand_color', sa.String(7), default='#4F46E5'))
op.add_column('user', sa.Column('invoice_footer', sa.Text()))

# Subscription transactions (for payment tracking)
op.create_table(
    'subscription_transaction',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id')),
    sa.Column('plan_id', sa.Integer(), sa.ForeignKey('subscription_plan.id')),
    sa.Column('amount', sa.Numeric(scale=2)),
    sa.Column('payment_ref', sa.String(120)),  # Paystack reference
    sa.Column('status', sa.String(20)),  # pending, success, failed
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now()),
)
```

#### 1.2 Models Update
```python
# app/models/models.py

class SubscriptionPlan(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))  # Free, Pro, Enterprise
    price: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    billing_period: Mapped[str] = mapped_column(String(20), default='monthly')
    max_invoices: Mapped[int | None]  # NULL = unlimited
    max_workers: Mapped[int | None]  # NULL = unlimited
    has_branding: Mapped[bool] = mapped_column(Boolean, default=False)
    has_payroll: Mapped[bool] = mapped_column(Boolean, default=False)
    has_reminders: Mapped[bool] = mapped_column(Boolean, default=False)
    has_analytics: Mapped[bool] = mapped_column(Boolean, default=False)
    has_api_access: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str]
    
    # Subscription
    subscription_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscription_plan.id")
    )
    subscription_status: Mapped[str] = mapped_column(String(20), default='trial')
    subscription_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    trial_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    
    # Usage tracking
    invoices_this_month: Mapped[int] = mapped_column(Integer, default=0)
    last_invoice_reset: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    
    # Branding (Premium feature)
    business_name: Mapped[str | None] = mapped_column(String(200))
    business_email: Mapped[str | None] = mapped_column(String(120))
    business_phone: Mapped[str | None] = mapped_column(String(32))
    business_address: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    brand_color: Mapped[str] = mapped_column(String(7), default='#4F46E5')
    invoice_footer: Mapped[str | None] = mapped_column(Text)
    
    created_at: Mapped[dt.datetime] = mapped_column(...)
    
    # Relationships
    subscription_plan: Mapped[SubscriptionPlan | None] = relationship("SubscriptionPlan")


class SubscriptionTransaction(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("subscription_plan.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(scale=2))
    payment_ref: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))  # pending, success, failed
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    user: Mapped[User] = relationship("User")
    plan: Mapped[SubscriptionPlan] = relationship("SubscriptionPlan")
```

#### 1.3 Subscription Service
```python
# app/services/subscription_service.py

from datetime import datetime, timedelta
from decimal import Decimal

class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_plan(self, user: User) -> SubscriptionPlan | None:
        """Get user's current subscription plan."""
        return user.subscription_plan
    
    def can_access_feature(self, user: User, feature: str) -> bool:
        """Check if user can access a premium feature."""
        plan = self.get_user_plan(user)
        
        # During trial, all features are accessible
        if user.subscription_status == 'trial':
            if user.trial_expires_at and user.trial_expires_at > datetime.now(timezone.utc):
                return True
        
        # Check subscription status
        if user.subscription_status not in ['active', 'trial']:
            return False
        
        # Check if subscription expired
        if user.subscription_expires_at and user.subscription_expires_at < datetime.now(timezone.utc):
            return False
        
        # Check plan features
        if not plan:
            return False  # No plan = Free tier
        
        feature_map = {
            'branding': plan.has_branding,
            'payroll': plan.has_payroll,
            'reminders': plan.has_reminders,
            'analytics': plan.has_analytics,
            'api_access': plan.has_api_access,
        }
        
        return feature_map.get(feature, False)
    
    def can_create_invoice(self, user: User) -> tuple[bool, str]:
        """Check if user can create more invoices this month."""
        plan = self.get_user_plan(user)
        
        # Reset counter if new month
        now = datetime.now(timezone.utc)
        if user.last_invoice_reset is None or user.last_invoice_reset.month != now.month:
            user.invoices_this_month = 0
            user.last_invoice_reset = now
            self.db.commit()
        
        # Trial or paid plans
        if user.subscription_status in ['trial', 'active']:
            if plan and plan.max_invoices is None:
                return True, "Unlimited invoices"
            
            if plan and user.invoices_this_month >= plan.max_invoices:
                return False, f"Monthly limit of {plan.max_invoices} invoices reached. Upgrade to create more."
        
        # Free tier (after trial)
        if user.subscription_status == 'expired' or plan is None:
            free_limit = 10
            if user.invoices_this_month >= free_limit:
                return False, f"Free tier limit of {free_limit} invoices reached. Upgrade to Pro for unlimited invoices."
        
        return True, "OK"
    
    def increment_invoice_count(self, user: User):
        """Increment user's invoice count for this month."""
        user.invoices_this_month += 1
        self.db.commit()
    
    def start_trial(self, user: User):
        """Start 14-day trial for new user."""
        user.subscription_status = 'trial'
        user.trial_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
        self.db.commit()
    
    def subscribe_to_plan(self, user: User, plan_id: int, payment_ref: str) -> SubscriptionTransaction:
        """Subscribe user to a plan after payment."""
        plan = self.db.query(SubscriptionPlan).get(plan_id)
        if not plan:
            raise ValueError("Invalid plan")
        
        # Create transaction record
        transaction = SubscriptionTransaction(
            user_id=user.id,
            plan_id=plan.id,
            amount=plan.price,
            payment_ref=payment_ref,
            status='pending'
        )
        self.db.add(transaction)
        
        # Update user subscription
        user.subscription_plan_id = plan.id
        user.subscription_status = 'active'
        user.subscription_started_at = datetime.now(timezone.utc)
        
        # Set expiry based on billing period
        if plan.billing_period == 'monthly':
            user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        elif plan.billing_period == 'yearly':
            user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        
        self.db.commit()
        return transaction
    
    def handle_subscription_payment(self, payment_ref: str, status: str):
        """Handle subscription payment webhook."""
        transaction = self.db.query(SubscriptionTransaction).filter(
            SubscriptionTransaction.payment_ref == payment_ref
        ).first()
        
        if not transaction:
            logger.warning(f"Transaction not found: {payment_ref}")
            return
        
        transaction.status = 'success' if status == 'success' else 'failed'
        
        if status != 'success':
            # Payment failed - revert subscription
            user = transaction.user
            user.subscription_status = 'expired'
            user.subscription_plan_id = None
        
        self.db.commit()
```

#### 1.4 Feature Guards (Middleware)
```python
# app/api/dependencies.py

from fastapi import HTTPException, Depends
from app.services.subscription_service import SubscriptionService, get_subscription_service

def require_feature(feature: str):
    """Dependency to check if user has access to a premium feature."""
    async def check_feature(
        current_user: User = Depends(get_current_user),
        subscription_service: SubscriptionService = Depends(get_subscription_service)
    ):
        if not subscription_service.can_access_feature(current_user, feature):
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires a premium subscription. Please upgrade to access {feature}."
            )
        return current_user
    return check_feature
```

### Phase 2: API Endpoints (Week 1)

#### 2.1 Subscription Endpoints
```python
# app/api/routes_subscription.py

@router.get("/plans")
async def list_plans(db: Session = Depends(get_db)):
    """Get all available subscription plans."""
    plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.active == True).all()
    return plans

@router.post("/subscribe/{plan_id}")
async def subscribe(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    subscription_service: SubscriptionService = Depends(get_subscription_service)
):
    """Initiate subscription to a plan."""
    plan = db.query(SubscriptionPlan).get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    
    # Create Paystack payment link for subscription
    payment_service = PaymentService(db)
    payment_link = payment_service.create_payment_link(
        amount=float(plan.price),
        email=current_user.phone + "@suopay.io",  # Temporary email
        reference=f"SUB-{current_user.id}-{int(time.time())}",
        metadata={
            "type": "subscription",
            "user_id": current_user.id,
            "plan_id": plan.id,
        }
    )
    
    return {"payment_url": payment_link, "plan": plan}

@router.get("/me/subscription")
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    subscription_service: SubscriptionService = Depends(get_subscription_service)
):
    """Get current user's subscription details."""
    plan = subscription_service.get_user_plan(current_user)
    
    return {
        "status": current_user.subscription_status,
        "plan": plan,
        "expires_at": current_user.subscription_expires_at,
        "trial_expires_at": current_user.trial_expires_at,
        "invoices_used": current_user.invoices_this_month,
        "invoices_limit": plan.max_invoices if plan else 10,
    }

@router.post("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel user's subscription."""
    current_user.subscription_status = 'cancelled'
    db.commit()
    return {"message": "Subscription cancelled. You will be downgraded to Free tier at the end of billing period."}
```

#### 2.2 Update Invoice Creation with Guards
```python
# app/api/routes_invoice.py

@router.post("/", response_model=schemas.InvoiceOut)
async def create_invoice(
    payload: schemas.InvoiceCreate,
    current_user: User = Depends(get_current_user),
    service: InvoiceService = Depends(get_invoice_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
):
    """Create invoice - check subscription limits."""
    # Check if user can create more invoices
    can_create, message = subscription_service.can_create_invoice(current_user)
    if not can_create:
        raise HTTPException(403, detail=message)
    
    # Create invoice
    invoice = service.create_invoice(issuer_id=current_user.id, data=payload.model_dump())
    
    # Increment counter
    subscription_service.increment_invoice_count(current_user)
    
    return invoice
```

#### 2.3 Branding Endpoints (Premium)
```python
# app/api/routes_branding.py

@router.put("/me/branding")
async def update_branding(
    branding: BrandingUpdate,
    current_user: User = Depends(require_feature("branding")),  # Premium check
    db: Session = Depends(get_db)
):
    """Update business branding (Pro and Enterprise only)."""
    current_user.business_name = branding.business_name
    current_user.business_email = branding.business_email
    current_user.business_phone = branding.business_phone
    current_user.business_address = branding.business_address
    current_user.brand_color = branding.brand_color
    current_user.invoice_footer = branding.invoice_footer
    db.commit()
    return {"message": "Branding updated"}

@router.post("/me/logo")
async def upload_logo(
    logo: UploadFile,
    current_user: User = Depends(require_feature("branding")),
    db: Session = Depends(get_db),
    s3: S3Client = Depends(get_s3_client)
):
    """Upload business logo (Pro and Enterprise only)."""
    logo_bytes = await logo.read()
    url = s3.upload_bytes(logo_bytes, f"logos/{current_user.id}/{logo.filename}")
    current_user.logo_url = url
    db.commit()
    return {"logo_url": url}
```

#### 2.4 Payroll Endpoints (Premium)
```python
# app/api/routes_payroll.py

@router.post("/workers")
async def add_worker(
    payload: schemas.WorkerCreate,
    current_user: User = Depends(require_feature("payroll")),  # Premium check
    service: PayrollService = Depends(get_payroll_service),
):
    """Add worker (Pro and Enterprise only)."""
    return service.add_worker(current_user.id, payload)

@router.post("/runs")
async def create_payroll_run(
    payload: schemas.PayrollRunCreate,
    current_user: User = Depends(require_feature("payroll")),
    service: PayrollService = Depends(get_payroll_service),
):
    """Create payroll run (Pro and Enterprise only)."""
    return service.create_payroll_run(current_user.id, payload)
```

### Phase 3: Seed Data (Week 1)

```python
# scripts/seed_subscription_plans.py

def seed_plans():
    db = SessionLocal()
    
    # Free Plan (default after trial)
    free_plan = SubscriptionPlan(
        name="Free",
        price=Decimal("0"),
        billing_period="monthly",
        max_invoices=10,
        max_workers=0,
        has_branding=False,
        has_payroll=False,
        has_reminders=False,
        has_analytics=False,
        has_api_access=False,
    )
    
    # Pro Plan
    pro_plan = SubscriptionPlan(
        name="Pro",
        price=Decimal("5000"),  # ₦5,000/month
        billing_period="monthly",
        max_invoices=None,  # Unlimited
        max_workers=10,
        has_branding=True,
        has_payroll=True,
        has_reminders=True,
        has_analytics=True,
        has_api_access=False,
    )
    
    # Enterprise Plan
    enterprise_plan = SubscriptionPlan(
        name="Enterprise",
        price=Decimal("20000"),  # ₦20,000/month
        billing_period="monthly",
        max_invoices=None,  # Unlimited
        max_workers=None,  # Unlimited
        has_branding=True,
        has_payroll=True,
        has_reminders=True,
        has_analytics=True,
        has_api_access=True,
    )
    
    db.add_all([free_plan, pro_plan, enterprise_plan])
    db.commit()
```

### Phase 4: Frontend (Week 2)

#### 4.1 Pricing Page
```typescript
// frontend/app/(marketing)/pricing/page.tsx

export default function PricingPage() {
  return (
    <div className="py-12">
      <h1 className="text-4xl font-bold text-center mb-12">
        Simple, Transparent Pricing
      </h1>
      
      <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
        {/* Free Tier */}
        <PricingCard
          name="Free"
          price="₦0"
          period="/forever"
          features={[
            "10 invoices per month",
            "Payment processing",
            "WhatsApp notifications",
            "Basic dashboard"
          ]}
          cta="Start Free"
        />
        
        {/* Pro Tier */}
        <PricingCard
          name="Pro"
          price="₦5,000"
          period="/month"
          popular={true}
          features={[
            "Unlimited invoices",
            "Custom branding & logo",
            "Payroll (up to 10 workers)",
            "Payment reminders",
            "Advanced analytics"
          ]}
          cta="Start 14-Day Trial"
        />
        
        {/* Enterprise Tier */}
        <PricingCard
          name="Enterprise"
          price="₦20,000"
          period="/month"
          features={[
            "Everything in Pro",
            "Unlimited workers",
            "API access",
            "Priority support",
            "Multi-user accounts"
          ]}
          cta="Start 14-Day Trial"
        />
      </div>
    </div>
  )
}
```

#### 4.2 Upgrade Modal
```typescript
// frontend/src/components/upgrade-modal.tsx

export function UpgradeModal({ feature }: { feature: string }) {
  return (
    <Modal>
      <h2>Upgrade to Pro</h2>
      <p>
        The {feature} feature is available on Pro and Enterprise plans.
      </p>
      <Link href="/pricing">
        <Button>View Plans</Button>
      </Link>
    </Modal>
  )
}
```

#### 4.3 Feature Guards in Frontend
```typescript
// frontend/src/hooks/use-subscription.ts

export function useSubscription() {
  const { data: subscription } = useQuery('/api/me/subscription')
  
  const canAccess = (feature: string) => {
    if (!subscription) return false
    return subscription.plan?.[`has_${feature}`] || false
  }
  
  const showUpgradeModal = (feature: string) => {
    // Show modal prompting upgrade
  }
  
  return { subscription, canAccess, showUpgradeModal }
}
```

---

## 🚀 Implementation Timeline

### Week 1: Backend Infrastructure
- Day 1-2: Database migration and models
- Day 3-4: Subscription service and feature guards
- Day 5: API endpoints and testing

### Week 2: Frontend
- Day 1-2: Pricing page and plan selection
- Day 3-4: Upgrade modals and feature guards
- Day 5: Payment integration and testing

### Week 3: Premium Features
- Day 1-2: Branding implementation (logo upload, custom colors)
- Day 3-4: Payroll frontend (dashboard, payslip generation)
- Day 5: End-to-end testing

### Week 4: Polish & Launch
- Day 1-2: Testing and bug fixes
- Day 3: Documentation
- Day 4: Deploy to production
- Day 5: Launch and monitoring

---

## 💰 Revenue Projections

### Conservative Estimates:
- **100 users**: 10 Pro (₦50k/mo) + 2 Enterprise (₦40k/mo) = **₦90,000/month**
- **500 users**: 50 Pro (₦250k/mo) + 10 Enterprise (₦200k/mo) = **₦450,000/month**
- **1000 users**: 100 Pro (₦500k/mo) + 25 Enterprise (₦500k/mo) = **₦1,000,000/month**

### Conversion Rate Assumptions:
- 10% of free users convert to paid
- 20% of paid users choose Enterprise

---

## ✅ Next Steps

1. **Approve this plan** and I'll start implementation
2. **Choose starting week**: Week 1 (backend) recommended
3. **Decide on pricing**: Confirm ₦5,000 Pro and ₦20,000 Enterprise
4. **Set trial period**: 14 days recommended

**Ready to implement the subscription system?** 🚀
