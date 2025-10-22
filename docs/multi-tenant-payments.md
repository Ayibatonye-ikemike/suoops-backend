# Multi-Tenant Payment Architecture

## Overview

SuoPay has been refactored from a single-tenant payment platform to a **multi-tenant SaaS platform**. Each business now uses their own Paystack account, with money flowing directly to their bank account - not through SuoPay.

### Why This Architecture?

1. **Regulatory Compliance**: SuoPay is NOT a fintech - we don't hold customer funds
2. **Business Model**: Revenue from subscriptions (₦2,500-50,000/month), not payment processing
3. **Transparency**: Each business maintains their direct relationship with Paystack
4. **Simplicity**: Paystack fees (1.5% + ₦100) paid by businesses from their transactions

## Payment Flow

```
Customer → Business's Paystack Account → Business's Bank Account
                                       (NOT through SuoPay)
```

## Implementation Status

### ✅ Completed

1. **Database Schema** (Migration 0006)
   - `paystack_secret_key` - Business's Paystack secret key
   - `paystack_public_key` - Business's Paystack public key  
   - `business_name` - Business name for reference
   - `bank_name` - Settlement bank name
   - `account_number` - Settlement account number

2. **Service Layer Refactoring**
   - `PaymentService.__init__(paystack_secret_key)` - Accepts business credentials
   - `PaymentRouter.__init__(paystack_secret_key, flutterwave_secret_key)` - Multi-tenant routing
   - `build_invoice_service(db, user_id)` - Fetches user's Paystack key from database
   - Falls back to platform credentials if business hasn't configured

3. **API Routes Updated**
   - `POST /invoices` - Uses current user's Paystack account
   - `GET /invoices` - Scoped to user's account
   - `PATCH /invoices/{id}` - Uses user's credentials for payment link regeneration
   - All routes now pass `current_user_id` to service factory

4. **WhatsApp Bot Integration**
   - Handler receives database session (not pre-built service)
   - Extracts `issuer_id` from incoming message
   - Builds invoice service on-demand with user's credentials
   - Each business's WhatsApp invoices use their own Paystack account

5. **Webhook Handling**
   - Updated to use `build_invoice_service(db, user_id=None)` temporarily
   - Falls back to platform credentials for now
   - See "Pending Work" below for multi-tenant webhook routing

### 🔴 Pending Work

#### 1. Paystack Credentials Management API (HIGH PRIORITY)

Businesses need a way to configure their Paystack credentials. Create these endpoints:

```python
# app/api/routes_paystack.py

@router.post("/users/me/paystack")
def set_paystack_credentials(
    credentials: PaystackCredentials,
    current_user_id: CurrentUserDep,
    db: DbDep,
):
    """
    Set business's Paystack credentials.
    
    Required fields:
    - paystack_secret_key: sk_live_... or sk_test_...
    - paystack_public_key: pk_live_... or pk_test_...
    
    Optional fields:
    - business_name: For display/reference
    - bank_name: Settlement bank
    - account_number: Settlement account
    """
    # TODO: Encrypt secret key before storing
    # TODO: Validate keys by making test API call to Paystack
    # TODO: Update user record in database
    pass


@router.get("/users/me/paystack")
def get_paystack_credentials(
    current_user_id: CurrentUserDep,
    db: DbDep,
):
    """
    Get configured Paystack credentials (secret key redacted).
    
    Returns:
    - paystack_public_key: Full public key
    - paystack_secret_key: "sk_***...***" (redacted)
    - business_name, bank_name, account_number
    - configured: true/false
    """
    pass


@router.delete("/users/me/paystack")
def remove_paystack_credentials(
    current_user_id: CurrentUserDep,
    db: DbDep,
):
    """
    Remove Paystack credentials.
    
    After removal, invoices will use platform default credentials.
    """
    pass
```

**Why This Matters:**
- Without this API, businesses can't configure their accounts
- Currently all businesses use platform default (SuoPay's Paystack)
- This is THE critical missing piece for multi-tenancy

**Security Considerations:**
- Encrypt `paystack_secret_key` at rest using Fernet or similar
- Never return full secret key in API responses
- Log credential changes for audit trail
- Validate keys by making test Paystack API call

#### 2. Multi-Tenant Webhook Routing (MEDIUM PRIORITY)

Current webhook handlers use `user_id=None`, falling back to platform credentials. We need to identify which business each webhook belongs to:

```python
# app/api/routes_webhooks.py

@router.post("/paystack")
async def paystack_webhook(request: Request, db: SessionDep):
    """
    Strategy 1: Extract user_id from payment reference
    
    If invoice references follow pattern: INV_{user_id}_{timestamp}
    We can parse user_id from the reference.
    """
    event = await request.json()
    reference = event.get("data", {}).get("reference")
    
    # Parse: INV_123_1704067200 → user_id = 123
    user_id = extract_user_id_from_reference(reference)
    
    # Use business's credentials to process webhook
    svc = build_invoice_service(db, user_id=user_id)
    svc.handle_payment_webhook(event)
```

**Alternative Strategy 2: Webhook URL Per Business**

```python
# Route: POST /webhooks/paystack/{user_id}

@router.post("/paystack/{user_id}")
async def paystack_webhook(user_id: int, request: Request, db: SessionDep):
    """
    Each business gets unique webhook URL from Paystack dashboard:
    - Business 123: https://api.suopay.io/webhooks/paystack/123
    - Business 456: https://api.suopay.io/webhooks/paystack/456
    """
    svc = build_invoice_service(db, user_id=user_id)
    svc.handle_payment_webhook(await request.json())
```

**Why This Matters:**
- Webhook signature verification uses business's Paystack secret key
- Payment confirmations must be processed with correct business context
- Currently all webhooks use platform credentials (wrong)

**Recommendation:**
Use Strategy 1 (reference parsing) - simpler for businesses to configure.

#### 3. Frontend Paystack Configuration UI (MEDIUM PRIORITY)

Create a settings page where businesses can:
1. Enter their Paystack API keys
2. View current configuration status
3. Test connection to Paystack
4. View settlement account details

**Location:** `frontend/app/(dashboard)/settings/paystack/page.tsx`

**Features:**
- Input fields for secret key, public key
- "Test Connection" button to validate keys
- Status indicator: ✅ Configured / ⚠️ Not Configured
- Help text: "Get your keys from Paystack Dashboard → Settings → API Keys"
- Link to Paystack signup/login

#### 4. Migration Deployment (HIGH PRIORITY)

Run migration 0006 on production:

```bash
# Local testing first
alembic upgrade head

# Then on Heroku
git push heroku main
heroku run alembic upgrade head -a suopay-backend
```

**Why This Matters:**
Without this migration, the `User` model has fields that don't exist in database - app will crash.

#### 5. Documentation Updates (LOW PRIORITY)

Update `docs/payment-and-bank-setup.md` to reflect multi-tenant architecture:
- How to get Paystack account
- Where to find API keys
- How to configure in SuoPay dashboard
- Settlement timeline expectations
- Webhook configuration (if using Strategy 2)

## Testing Checklist

### Local Testing

1. **Run Migration 0006**
   ```bash
   alembic upgrade head
   ```

2. **Test Without Credentials** (Falls back to platform default)
   ```bash
   curl -X POST http://localhost:8000/invoices \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"amount": 5000, "customer_email": "test@example.com"}'
   ```

3. **Configure Business Credentials**
   ```sql
   UPDATE users 
   SET paystack_secret_key = 'sk_test_your_key',
       paystack_public_key = 'pk_test_your_key'
   WHERE id = 1;
   ```

4. **Test With Business Credentials**
   ```bash
   # Same curl as above - should now use business's Paystack account
   # Check logs for: "Using business's own Paystack key for user 1"
   ```

5. **Test WhatsApp Invoice Creation**
   ```bash
   # Send WhatsApp message: "Invoice John Doe 50000 for website design"
   # Check logs for user_id extraction and service building
   ```

### Production Testing

1. **Deploy to Heroku**
   ```bash
   git push heroku main
   heroku run alembic upgrade head -a suopay-backend
   ```

2. **Configure Test Business**
   - Create test user account
   - Add Paystack test keys via API (once endpoint exists)
   - Create invoice via API
   - Verify payment link uses business's Paystack account

3. **Test Webhook Flow**
   - Make test payment
   - Check webhook received and processed correctly
   - Verify invoice status updated
   - Confirm WhatsApp receipt sent

## Rollback Plan

If multi-tenant approach causes issues:

```bash
# Revert migration 0006
alembic downgrade -1

# Revert code changes
git revert 7794983f
```

Then deploy and restart:
```bash
git push heroku main
heroku restart -a suopay-backend
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         SuoPay Platform                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐       ┌──────────────┐                    │
│  │  Business A  │       │  Business B  │                    │
│  ├──────────────┤       ├──────────────┤                    │
│  │ Paystack Key │       │ Paystack Key │                    │
│  │ sk_live_AAA  │       │ sk_live_BBB  │                    │
│  └──────┬───────┘       └──────┬───────┘                    │
│         │                      │                             │
│         ▼                      ▼                             │
│  ┌─────────────────────────────────────────┐                │
│  │     InvoiceService (per request)        │                │
│  │  • Fetches user's Paystack key          │                │
│  │  • Creates payment link with user's key │                │
│  └─────────────────────────────────────────┘                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Payment Link
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       Customer                                │
│                                                               │
│  Pays via: Business A's Paystack → Business A's Bank Account │
│       OR:  Business B's Paystack → Business B's Bank Account │
│                                                               │
│           (Money NEVER goes through SuoPay)                  │
└─────────────────────────────────────────────────────────────┘
```

## FAQ

### Q: What happens if a business doesn't configure Paystack?
**A:** Their invoices use SuoPay's platform Paystack account as fallback. Money would go to SuoPay's account, which we DON'T want long-term. This is why credential configuration is high priority.

### Q: Can businesses use Paystack test keys?
**A:** Yes! Test keys (sk_test_...) work for development and testing. Payments won't be real.

### Q: What about Flutterwave?
**A:** Same architecture - `flutterwave_secret_key` field can be added to User model. Currently only Paystack is fully implemented.

### Q: How do we handle webhook signature verification?
**A:** Each webhook is verified using the business's Paystack secret key (extracted from payment reference or webhook URL).

### Q: What if two businesses use the same Paystack account?
**A:** Technically possible but not recommended. Each business should have their own Paystack account for proper accounting and settlement.

### Q: Do we still need platform Paystack credentials?
**A:** Yes, as fallback for:
- Businesses without configured credentials
- Internal testing
- Demo accounts

## Next Steps

**Priority Order:**
1. ✅ Complete service layer refactoring (DONE)
2. ✅ Update API routes (DONE)
3. ✅ Update WhatsApp bot (DONE)
4. 🔴 **Create Paystack credentials management API** (NEXT)
5. 🔴 **Deploy migration 0006 to production** (NEXT)
6. 🟡 Implement multi-tenant webhook routing
7. 🟡 Build frontend settings UI
8. 🟢 Update documentation

**Estimated Time to Full Multi-Tenancy:**
- Credentials API: 2 hours
- Webhook routing: 2 hours  
- Frontend UI: 3 hours
- Testing & deployment: 2 hours
**Total: ~9 hours**

## Conclusion

The multi-tenant architecture is **60% complete**:
- ✅ Database schema ready
- ✅ Service layer refactored
- ✅ API routes updated
- ✅ WhatsApp integration updated
- 🔴 Credentials management API missing (critical)
- 🔴 Webhook routing incomplete
- 🔴 Frontend UI missing

**The app will continue working with platform credentials as fallback**, but businesses can't yet configure their own Paystack accounts until we build the credentials management API.
