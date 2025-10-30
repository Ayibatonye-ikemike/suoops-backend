# Feature Gating & Subscription Plans

## Overview

SuoOps uses a tiered subscription model where the **FREE tier** allows only **5 invoices per month**, and all premium features require a paid subscription.

## Subscription Tiers

| Plan | Monthly Price | Invoices/Month | Premium Features |
|------|---------------|----------------|------------------|
| **FREE** | ₦0 | 5 | ❌ No |
| **STARTER** | ₦2,500 | 100 | ✅ Yes |
| **PRO** | ₦7,500 | 1,000 | ✅ Yes |
| **BUSINESS** | ₦15,000 | 3,000 | ✅ Yes |
| **ENTERPRISE** | ₦50,000 | Unlimited | ✅ Yes |

## Features by Tier

### Free Tier (₦0/month)
✅ **Included:**
- 5 invoices per month
- Manual invoice creation (text/form)
- WhatsApp bot for invoice creation
- PDF invoice generation
- Email notifications
- Basic invoice management

❌ **Not Included:**
- Photo invoice OCR
- Voice message invoices
- Custom branding
- Priority support
- More than 5 invoices/month

### Paid Tiers (Starter, Pro, Business, Enterprise)
✅ **All Free features PLUS:**
- 📸 **Photo Invoice OCR** - Upload receipt photos, automatically extract data
- 🎙️ **Voice Invoices** - Send WhatsApp voice notes to create invoices
- 🎨 **Custom Branding** - Add your logo to invoices
- 💬 **Priority Support** - Faster response times
- 📊 **Higher Invoice Limits** - 100 to unlimited invoices/month

## How Feature Gating Works

### 1. Invoice Creation Limits

**All tiers** (including free) are limited by monthly invoice counts:

```python
# Example: Creating an invoice
POST /invoices/
```

**Response if limit reached (FREE tier):**
```json
{
  "error": "invoice_limit_reached",
  "message": "You've reached the free tier limit of 5 invoices per month. Upgrade to a paid plan to create more invoices and unlock premium features.",
  "current_count": 5,
  "limit": 5,
  "current_plan": "free",
  "upgrade_url": "/subscription/initialize"
}
```

### 2. Premium Features (Paid Plans Only)

#### Photo Invoice OCR

```python
POST /ocr/parse
POST /ocr/create-invoice
```

**Response if FREE tier:**
```json
{
  "error": "premium_feature_required",
  "message": "Photo invoice OCR is only available on paid plans. Upgrade to unlock this feature.",
  "current_plan": "free",
  "upgrade_url": "/subscription/initialize"
}
```

#### Voice Message Invoices (WhatsApp)

When a FREE tier user sends a voice note:

```
🔒 Voice Invoice Feature

Voice message invoices are only available on paid plans.

✅ Upgrade your plan to unlock:
• Voice note invoices
• Photo invoices (OCR)
• More monthly invoices
• Priority support

Visit suoops.com/dashboard/subscription to upgrade!
```

### 3. Check Feature Access

Get current user's feature access and limits:

```python
GET /user/me/features
```

**Response:**
```json
{
  "user_id": 123,
  "current_plan": "free",
  "plan_price": 0,
  "is_free_tier": true,
  "features": {
    "invoices_per_month": 5,
    "photo_invoice_ocr": false,
    "voice_invoice": false,
    "whatsapp_bot": true,
    "email_notifications": true,
    "pdf_generation": true,
    "custom_branding": false,
    "priority_support": false
  },
  "invoice_usage": {
    "used_this_month": 3,
    "limit": 5,
    "remaining": 2,
    "can_create_more": true,
    "limit_message": null
  },
  "upgrade_available": true,
  "upgrade_url": "/subscription/initialize"
}
```

## Implementation Details

### Backend Components

1. **`app/utils/feature_gate.py`** - Core feature gating logic
   - `FeatureGate` class for checking user permissions
   - `require_paid_plan()` - Raises 403 if user is on free tier
   - `check_invoice_limit()` - Raises 403 if invoice limit reached
   - Tracks monthly invoice counts

2. **Protected Endpoints:**
   - `POST /invoices/` - Invoice limit check
   - `POST /ocr/parse` - Requires paid plan
   - `POST /ocr/create-invoice` - Requires paid plan + invoice limit
   - WhatsApp voice messages - Requires paid plan

3. **`app/models/models.py`** - Subscription plan properties
   - `SubscriptionPlan.has_premium_features` - Boolean check
   - `SubscriptionPlan.features` - Dict of all feature flags
   - `SubscriptionPlan.invoice_limit` - Monthly invoice limits

### Usage in Code

```python
from app.utils.feature_gate import FeatureGate, require_paid_plan, check_invoice_limit

# Check if user has paid plan
require_paid_plan(db, user_id, "Feature Name")

# Check invoice creation limit
check_invoice_limit(db, user_id)

# Get detailed information
gate = FeatureGate(db, user_id)
if gate.is_paid_tier():
    # Allow premium feature
    pass
```

## Frontend Integration

### Show Feature Locks

Display lock icons (🔒) on premium features for free tier users:

```tsx
// Check user's plan
const { data: features } = useQuery('/user/me/features');

// Show upgrade prompt if feature not available
{!features.features.photo_invoice_ocr && (
  <div className="bg-yellow-50 p-4 rounded">
    <p>🔒 Photo invoices require a paid plan</p>
    <Button href="/subscription">Upgrade Now</Button>
  </div>
)}
```

### Handle Errors Gracefully

```tsx
try {
  await uploadPhoto(file);
} catch (error) {
  if (error.response?.data?.error === 'premium_feature_required') {
    // Show upgrade modal
    showUpgradeModal(error.response.data);
  } else if (error.response?.data?.error === 'invoice_limit_reached') {
    // Show limit reached message
    showLimitReachedModal(error.response.data);
  }
}
```

## Testing Feature Gating

### Test Invoice Limits (Free Tier)

```python
# Create 5 invoices (should succeed)
for i in range(5):
    response = client.post("/invoices/", json=invoice_data, headers=auth_headers)
    assert response.status_code == 200

# 6th invoice should fail
response = client.post("/invoices/", json=invoice_data, headers=auth_headers)
assert response.status_code == 403
assert response.json()["error"] == "invoice_limit_reached"
```

### Test Premium Feature Access

```python
# Free tier user attempts OCR
response = client.post("/ocr/parse", files={"file": image}, headers=free_user_headers)
assert response.status_code == 403
assert response.json()["error"] == "premium_feature_required"

# Paid tier user attempts OCR
response = client.post("/ocr/parse", files={"file": image}, headers=paid_user_headers)
assert response.status_code == 200
```

## Upgrade Flow

1. User hits feature limit or tries premium feature
2. API returns 403 with upgrade URL
3. Frontend shows upgrade modal with plan comparison
4. User clicks "Upgrade Now" → redirects to `/subscription/initialize`
5. User selects plan and completes payment via Paystack
6. Webhook updates user's plan in database
7. User now has access to premium features

## Database Schema

```sql
-- User table includes subscription fields
CREATE TABLE "user" (
    id SERIAL PRIMARY KEY,
    plan VARCHAR NOT NULL DEFAULT 'free',  -- free, starter, pro, business, enterprise
    invoices_this_month INTEGER DEFAULT 0,
    usage_reset_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- ... other fields
);

-- Invoice limit tracking uses created_at timestamp
SELECT COUNT(*) FROM invoice 
WHERE issuer_id = ? 
  AND EXTRACT(MONTH FROM created_at) = EXTRACT(MONTH FROM NOW())
  AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM NOW());
```

## Monthly Reset

Invoice counts reset automatically on the 1st of each month (handled in `FeatureGate.get_monthly_invoice_count()` which queries by month/year).

No cron job needed - calculation is done on-demand by filtering invoices created in current month/year.

## Monitoring & Analytics

Track these metrics:

1. **Conversion Rate**: Free users who upgrade to paid
2. **Feature Blocking**: How often users hit limits
3. **Popular Premium Features**: Which features drive upgrades
4. **Churn**: Users who downgrade from paid to free

```python
# Example analytics queries
- COUNT users WHERE plan = 'free' AND attempted_premium_feature = true
- COUNT invoice_creation_attempts WHERE status = 'limit_reached'
- AVG(time_to_upgrade) WHERE upgraded = true
```

## Future Enhancements

- [ ] Add grace period (e.g., 3 extra invoices before hard block)
- [ ] Implement annual billing with discount
- [ ] Add team/multi-user plans
- [ ] Usage-based pricing for enterprise
- [ ] Trial periods for premium features
- [ ] Referral credits for free tier users
