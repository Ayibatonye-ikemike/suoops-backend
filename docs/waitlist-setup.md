# SuoOps Waitlist Setup Guide

## Overview
While waiting for Meta WhatsApp Business verification, capture early users via waitlist. Two options available:

## Option 1: Google Forms (Quickest - 5 minutes)

### Step 1: Create Google Form

1. **Go to:** https://forms.google.com
2. **Click:** "Blank form" or use template
3. **Form Title:** "SuoOps Waitlist - Join Early Access"

### Step 2: Add Form Fields

**Required Fields:**
```
1. Full Name (Short answer)
   - Required: Yes
   
2. Email Address (Short answer)
   - Required: Yes
   - Validation: Response validation → Text → Email
   
3. Phone Number (Short answer)
   - Required: Yes
   - Help text: "WhatsApp number (e.g., +2348012345678)"
   
4. Business Name (Short answer)
   - Required: No
   - Help text: "Optional: Your business name"
   
5. How many invoices per month? (Multiple choice)
   - Required: No
   - Options:
     • 1-10 invoices/month
     • 11-50 invoices/month
     • 51-100 invoices/month
     • 100+ invoices/month
   
6. What interests you most? (Checkboxes)
   - Required: No
   - Options:
     • Voice note invoicing
     • WhatsApp automation
     • Payment tracking
     • Multi-currency support
     • Team collaboration
```

### Step 3: Customize Response Message

**Settings → Presentation:**
```
✅ Show progress bar
✅ Show link to submit another response

Confirmation message:
"🎉 You're on the list!

Thanks for joining the SuoOps waitlist. We'll notify you via email and WhatsApp when we launch.

While you wait:
• Follow us on Twitter: @suoops
• Questions? Email: info@suoops.com

Expected launch: [Your date]

- The SuoOps Team"
```

### Step 4: Get Form Link

1. Click **"Send"** button (top right)
2. Click **link icon** (🔗)
3. Click **"Shorten URL"**
4. Copy link (e.g., `https://forms.gle/abc123`)

### Step 5: Update Landing Page

Add to `frontend/app/page.tsx`:

```tsx
// Replace existing CTA button with:
<a
  href="https://forms.gle/YOUR_FORM_ID"
  target="_blank"
  rel="noopener noreferrer"
  className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-8 py-4 text-lg font-semibold text-white shadow-xl transition-all duration-200 hover:bg-blue-700 hover:shadow-2xl hover:scale-105"
>
  Join Waitlist - Coming Soon! 🚀
</a>

// Add notice banner at top:
<div className="bg-yellow-50 border-b border-yellow-200 px-4 py-3 text-center">
  <p className="text-sm text-yellow-800">
    ⏳ <strong>Pre-launch:</strong> Join our waitlist to get early access when we launch!
  </p>
</div>
```

### Step 6: Track Responses

**View Responses:**
1. Go to your Google Form
2. Click **"Responses"** tab
3. View summary or individual responses

**Export to Spreadsheet:**
1. Click green **Sheets icon** in Responses tab
2. Creates linked Google Sheet automatically
3. All responses sync in real-time

**Set Up Email Notifications:**
1. In Google Sheet, click **Tools → Notification rules**
2. Select: "A user submits a form"
3. Email: Your email address
4. Frequency: "Notify me immediately"

---

## Option 2: Built-in Waitlist (Database-backed)

### Advantages
- ✅ Own your data (PostgreSQL database)
- ✅ No external dependencies
- ✅ Custom admin dashboard
- ✅ Automated email notifications
- ✅ Export to CSV anytime
- ✅ Integration with existing auth system

### Database Migration

Create waitlist table:

```sql
-- alembic/versions/0005_add_waitlist.py
CREATE TABLE waitlist (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20) NOT NULL,
    business_name VARCHAR(100),
    monthly_invoices VARCHAR(50),
    interests TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notified BOOLEAN DEFAULT FALSE,
    notes TEXT
);

CREATE INDEX idx_waitlist_email ON waitlist(email);
CREATE INDEX idx_waitlist_created_at ON waitlist(created_at DESC);
```

### Backend API

```python
# app/models/models.py
class WaitlistEntry(Base):
    __tablename__ = "waitlist"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=False)
    business_name = Column(String(100), nullable=True)
    monthly_invoices = Column(String(50), nullable=True)
    interests = Column(ARRAY(String), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    notified = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

# app/models/schemas.py
class WaitlistCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    business_name: str | None = None
    monthly_invoices: str | None = None
    interests: list[str] | None = None

class WaitlistOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    business_name: str | None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# app/api/routes_waitlist.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import models, schemas
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

@router.post("/", response_model=schemas.WaitlistOut, status_code=201)
async def join_waitlist(
    data: schemas.WaitlistCreate,
    db: Session = Depends(get_db)
):
    """Join the SuoOps waitlist"""
    
    # Check if already registered
    existing = db.query(models.WaitlistEntry).filter(
        models.WaitlistEntry.email == data.email
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already registered on waitlist"
        )
    
    # Create entry
    entry = models.WaitlistEntry(**data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    # Send confirmation email
    notification_service = NotificationService()
    await notification_service.send_waitlist_confirmation(
        email=data.email,
        name=data.full_name
    )
    
    return entry

@router.get("/count")
async def get_waitlist_count(db: Session = Depends(get_db)):
    """Get total waitlist signups"""
    count = db.query(models.WaitlistEntry).count()
    return {"count": count}

# Admin endpoint (add authentication)
@router.get("/", response_model=list[schemas.WaitlistOut])
async def list_waitlist(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
    # Add: current_user: CurrentUserDep (only admins)
):
    """List all waitlist entries (admin only)"""
    entries = db.query(models.WaitlistEntry)\
        .order_by(models.WaitlistEntry.created_at.desc())\
        .offset(skip)\
        .limit(limit)\
        .all()
    return entries
```

### Frontend Waitlist Form

```tsx
// frontend/app/waitlist/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function WaitlistPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    phone: '',
    business_name: '',
    monthly_invoices: '',
    interests: [] as string[],
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await fetch('https://api.suoops.com/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to join waitlist');
      }

      router.push('/waitlist/success');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleInterest = (interest: string) => {
    setFormData(prev => ({
      ...prev,
      interests: prev.interests.includes(interest)
        ? prev.interests.filter(i => i !== interest)
        : [...prev.interests, interest]
    }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            Join the SuoOps Waitlist 🚀
          </h1>
          <p className="text-lg text-gray-600">
            Be the first to experience voice-powered invoicing on WhatsApp
          </p>
          <div className="mt-4 inline-flex items-center gap-2 bg-yellow-100 border border-yellow-300 rounded-full px-4 py-2">
            <span className="text-yellow-800 text-sm font-medium">
              ⏳ Launching Soon • Get Early Access
            </span>
          </div>
        </div>

        {/* Form */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800 text-sm">
                {error}
              </div>
            )}

            {/* Full Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Full Name *
              </label>
              <input
                type="text"
                required
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="John Doe"
              />
            </div>

            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Email Address *
              </label>
              <input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="john@example.com"
              />
            </div>

            {/* Phone */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                WhatsApp Number *
              </label>
              <input
                type="tel"
                required
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="+2348012345678"
              />
              <p className="mt-1 text-xs text-gray-500">Include country code</p>
            </div>

            {/* Business Name (Optional) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Business Name (Optional)
              </label>
              <input
                type="text"
                value={formData.business_name}
                onChange={(e) => setFormData({ ...formData, business_name: e.target.value })}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Acme Inc."
              />
            </div>

            {/* Monthly Invoices */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                How many invoices per month?
              </label>
              <select
                value={formData.monthly_invoices}
                onChange={(e) => setFormData({ ...formData, monthly_invoices: e.target.value })}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Select range</option>
                <option value="1-10">1-10 invoices/month</option>
                <option value="11-50">11-50 invoices/month</option>
                <option value="51-100">51-100 invoices/month</option>
                <option value="100+">100+ invoices/month</option>
              </select>
            </div>

            {/* Interests */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                What interests you most?
              </label>
              <div className="space-y-2">
                {[
                  'Voice note invoicing',
                  'WhatsApp automation',
                  'Payment tracking',
                  'Multi-currency support',
                  'Team collaboration'
                ].map(interest => (
                  <label key={interest} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.interests.includes(interest)}
                      onChange={() => toggleInterest(interest)}
                      className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-700">{interest}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-4 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Joining...
                </>
              ) : (
                '🚀 Join Waitlist'
              )}
            </button>
          </form>

          {/* Features Preview */}
          <div className="mt-8 pt-8 border-t border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              What you'll get:
            </h3>
            <ul className="space-y-3 text-sm text-gray-600">
              <li className="flex items-start gap-2">
                <span className="text-green-600">✓</span>
                <span>Early access to WhatsApp invoicing</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-600">✓</span>
                <span>Exclusive launch pricing (50% off first 3 months)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-600">✓</span>
                <span>Priority support and onboarding</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-600">✓</span>
                <span>Beta testing new features first</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Social Proof */}
        <div className="mt-8 text-center text-sm text-gray-600">
          <p>Join <strong id="waitlist-count">50+</strong> businesses already waiting</p>
        </div>
      </div>
    </div>
  );
}

// frontend/app/waitlist/success/page.tsx
export default function WaitlistSuccessPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-blue-100 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl p-8 text-center">
        <div className="text-6xl mb-4">🎉</div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          You're on the list!
        </h1>
        <p className="text-gray-600 mb-6">
          Thanks for joining the SuoOps waitlist. We'll notify you via email and WhatsApp when we launch.
        </p>
        
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <p className="text-sm text-blue-800">
            <strong>What's next?</strong><br/>
            We'll send you updates on our progress and notify you when we're ready to onboard you.
          </p>
        </div>

        <div className="space-y-3">
          <a
            href="/"
            className="block w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition-colors"
          >
            Back to Home
          </a>
          <a
            href="mailto:info@suoops.com"
            className="block w-full border border-gray-300 hover:border-gray-400 text-gray-700 font-semibold py-3 rounded-lg transition-colors"
          >
            Questions? Contact Us
          </a>
        </div>
      </div>
    </div>
  );
}
```

---

## Notification Email Template

```python
# app/services/notification_service.py

async def send_waitlist_confirmation(self, email: str, name: str) -> bool:
    """Send waitlist confirmation email"""
    smtp_config = self._get_smtp_config()
    if not smtp_config:
        return False
    
    msg = MIMEMultipart()
    msg['From'] = settings.FROM_EMAIL
    msg['To'] = email
    msg['Subject'] = "🎉 You're on the SuoOps Waitlist!"
    
    body = f"""
Hello {name}! 👋

Welcome to the SuoOps waitlist! You're one step closer to transforming how you create invoices.

🚀 What happens next?
1. We'll notify you when we launch (expected: [Your date])
2. You'll get exclusive early access
3. Special launch pricing (50% off first 3 months)

💡 While you wait:
• Follow updates: twitter.com/suoops
• Watch demo videos: youtube.com/@suoops
• Questions? Reply to this email

⚡ What you'll be able to do:
• Create invoices via WhatsApp voice notes or text
• Automatic payment tracking
• PDF generation and email delivery
• Real-time notifications

Thanks for believing in us! We can't wait to have you on board.

---
The SuoOps Team
info@suoops.com
suoops.com
"""
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
            server.starttls()
            server.login(smtp_config["user"], smtp_config["password"])
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Failed to send waitlist email: {e}")
        return False
```

---

## Launch Notification System

When ready to go live, notify all waitlist users:

```python
# scripts/notify_waitlist.py
"""
Notify all waitlist users that SuoOps is live.
Usage: heroku run python scripts/notify_waitlist.py
"""
import asyncio
from app.db.session import SessionLocal
from app.models.models import WaitlistEntry
from app.services.notification_service import NotificationService

async def notify_all_waitlist():
    db = SessionLocal()
    notification_service = NotificationService()
    
    entries = db.query(WaitlistEntry).filter(
        WaitlistEntry.notified == False
    ).all()
    
    print(f"Found {len(entries)} users to notify")
    
    for entry in entries:
        try:
            # Send launch email
            await notification_service.send_launch_notification(
                email=entry.email,
                name=entry.full_name
            )
            
            # Mark as notified
            entry.notified = True
            db.commit()
            
            print(f"✓ Notified {entry.email}")
        except Exception as e:
            print(f"✗ Failed to notify {entry.email}: {e}")
    
    db.close()
    print(f"\n🎉 Done! Notified {len(entries)} users")

if __name__ == "__main__":
    asyncio.run(notify_waitlist())
```

---

## Which Option to Choose?

### Use Google Forms if:
- ✅ Need quick setup (< 5 minutes)
- ✅ Don't want to write code
- ✅ Small expected waitlist (< 1,000)
- ✅ Just collecting basic info

### Use Built-in Waitlist if:
- ✅ Want full control of data
- ✅ Plan to send automated emails
- ✅ Want admin dashboard
- ✅ Large expected waitlist (1,000+)
- ✅ Need integration with main platform

---

## Recommended Hybrid Approach

1. **Start with Google Forms** (Day 1):
   - Get waitlist live in 5 minutes
   - Start collecting signups immediately
   - No coding required

2. **Migrate to Database** (When you have time):
   - Export Google Sheet to CSV
   - Import into PostgreSQL
   - Switch form to point to API
   - Keep both running (Google Form still works)

---

## Marketing the Waitlist

**Landing Page Updates:**
```
Replace "Get Started" → "Join Waitlist"
Add banner: "⏳ Pre-launch: Limited early access spots available"
Show counter: "Join 50+ businesses already waiting"
```

**Social Media:**
```
Twitter/LinkedIn: "🚀 Launching soon! Join the SuoOps waitlist for early access to voice-powered invoicing on WhatsApp. Link in bio."

Instagram: Share design mockups with "Coming soon" badge
```

**Email Signature:**
```
---
Mike | SuoOps
Launching Soon - Join Waitlist: suoops.com/waitlist
Voice-powered invoicing on WhatsApp
```

---

## Timeline Example

**Week 1-2 (Now):**
- Set up Google Form waitlist
- Update landing page
- Start collecting signups

**Week 3-4 (While waiting for Meta):**
- Build database-backed waitlist
- Import Google Form responses
- Create admin dashboard

**Launch Day:**
- Run notify_waitlist.py script
- Send launch emails to all
- Open WhatsApp bot to waitlist first
- Gradual public rollout

---

**Next steps:**
1. Which option do you want to start with? (Google Forms or built-in)
2. I can help you set up either one right now!
