# WhatsApp Bot Connection Guide

## 🎯 How Businesses Connect to Your WhatsApp Bot

Your platform uses **Model 1: Centralized Bot** - one WhatsApp number serves ALL businesses.

---

## 📱 Connection Architecture

```
┌─────────────────────────────────────────────────────┐
│  YOUR PLATFORM (suoops.com)                          │
│                                                      │
│  WhatsApp Business Number: +234 XXX XXX XXXX       │
│  (One number for entire platform)                   │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
   Business 1            Business 2
   +2348011111111        +2348022222222
        │                     │
   Sends message        Sends message
        │                     │
        └──────────┬──────────┘
                   │
            ┌──────▼───────┐
            │  Bot Checks  │
            │  Phone Number│
            └──────┬───────┘
                   │
        ┌──────────┴──────────┐
        │                     │
   User DB Lookup        User DB Lookup
   Phone: +2348011111111  Phone: +2348022222222
   → User ID: 1           → User ID: 2
        │                     │
   Invoice for User 1    Invoice for User 2
```

---

## 🔧 Current Implementation Issue

**Problem**: The code expects `issuer_id` in the webhook payload, but WhatsApp doesn't send business IDs automatically.

**Solution Needed**: Link WhatsApp phone number to User ID in your database.

---

## ✅ How to Fix (Database Linkage)

### Step 1: Add WhatsApp Phone to User Profile

Businesses need to register their WhatsApp number in their profile:

**Database Schema** (already in your `User` model):
```python
class User(Base):
    id: int
    email: str
    phone: str  # ← Business owner's WhatsApp number
    business_name: str
    # ... other fields
```

### Step 2: Update `_resolve_issuer_id()` Method

Replace the current implementation with phone number lookup:

```python
def _resolve_issuer_id(self, sender_phone: str) -> int | None:
    """
    Resolve business owner ID from WhatsApp phone number.
    
    Args:
        sender_phone: WhatsApp number (e.g., "+2348012345678")
    
    Returns:
        User ID of the business owner, or None if not found
    """
    from app.models import models
    
    # Clean phone number (remove + and spaces)
    clean_phone = sender_phone.replace("+", "").replace(" ", "")
    
    # Look up user by phone number
    user = (
        self.db.query(models.User)
        .filter(models.User.phone == clean_phone)
        .first()
    )
    
    if user:
        logger.info(f"Resolved WhatsApp {sender_phone} → User ID {user.id}")
        return user.id
    
    logger.warning(f"No user found for WhatsApp number: {sender_phone}")
    return None
```

### Step 3: Update `handle_message()` Call

```python
async def handle_message(self, sender: str, body: str, payload: dict):
    """Handle incoming text message."""
    logger.info(f"[WhatsApp] Message from {sender}: {body}")
    
    # Resolve business owner ID from phone number
    issuer_id = self._resolve_issuer_id(sender)  # ← Use sender phone
    
    if issuer_id is None:
        self.client.send_text(
            sender,
            "👋 Welcome! To use this bot, please register at suoops.com first.\n\n"
            "Then add this WhatsApp number to your profile."
        )
        return
    
    # Continue with NLP parsing...
```

---

## 📋 Business Onboarding Flow

### For New Businesses:

1. **Register on Web Platform**
   - Go to `https://suoops.com/register`
   - Create account with email & password
   - Provide business details

2. **Add WhatsApp Number**
   - Go to Settings → Profile
   - Add WhatsApp number: `+2348012345678`
   - Save settings

3. **Start Sending Messages**
   - Send WhatsApp to platform number: `+234XXXXXXXX`
   - Bot recognizes phone number → Links to account
   - Invoice created automatically

### Message Format:
```
"Invoice Jane 50000 naira for logo design"
```

Or voice note:
```
🎤 "Invoice Jane, fifty thousand naira for logo design"
```

---

## 🔐 Security Considerations

### Phone Number Verification (Recommended)

Add verification step to prevent abuse:

```python
class User(Base):
    phone: str
    phone_verified: bool = False  # Add this field
    phone_verification_code: str = None
```

**Verification Flow:**
1. Business adds phone number in settings
2. Platform sends SMS/WhatsApp code
3. Business enters code to verify
4. Only verified phones can use bot

---

## 💡 Alternative: QR Code Connection

For easier onboarding:

1. **Generate QR Code** for each business
2. **QR Code contains**: Business ID + Auth token
3. **Business scans QR** with WhatsApp
4. **Platform links** WhatsApp number to business

**Implementation:**
```python
# Generate QR code with deep link
qr_data = f"https://wa.me/{PLATFORM_NUMBER}?text=CONNECT_{user_id}_{auth_token}"
# Display QR code in dashboard
```

---

## 📊 Current Status

| Feature | Status | Notes |
|---------|--------|-------|
| WhatsApp webhook endpoint | ✅ Implemented | `/webhooks/whatsapp` |
| Message parsing (NLP) | ✅ Working | Text & voice |
| Voice transcription | ✅ Working | OpenAI Whisper |
| Invoice creation | ✅ Working | Full flow |
| **Phone → User lookup** | ❌ **NEEDED** | Missing database link |
| Unregistered user handling | ⚠️ Partial | Needs friendly message |

---

## 🚀 Quick Implementation (5 minutes)

Want me to implement the phone number lookup now? I can:

1. ✅ Update `_resolve_issuer_id()` to use phone lookup
2. ✅ Add friendly message for unregistered users
3. ✅ Update frontend to show WhatsApp connection status
4. ✅ Deploy to Render

Just say "implement phone lookup" and I'll do it! 🎯

---

## 📞 WhatsApp Business API Setup (Separate Task)

To get the platform WhatsApp number working, you need:

1. **Meta Business Account** (free)
2. **WhatsApp Business App** (approved by Meta)
3. **Phone Number** (can use your existing number)
4. **Webhook URL**: `https://api.suoops.com/webhooks/whatsapp`

**Time to setup**: 1-2 hours  
**Cost**: Free (up to 1,000 conversations/month)

See `docs/whatsapp-setup.md` for detailed setup guide.

---

## 🎯 Recommended Next Steps

1. **Implement phone number lookup** (5 minutes)
2. **Test with your own WhatsApp** (10 minutes)
3. **Set up Meta WhatsApp Business** (1-2 hours)
4. **Deploy and go live!** 🚀

Let me know when you're ready to proceed!
