# SuoOps User Guide - How It All Works

**Simple, hands-free invoicing for Nigerian businesses**

---

## 🎯 What is SuoOps?

SuoOps helps you create and send invoices to customers without typing, calculating, or designing anything. Just tell us what you sold (via WhatsApp, voice, text, or photo), and we handle the rest.

---

## 📱 Four Ways to Create an Invoice

### 1️⃣ WhatsApp Text Message (Easiest)

**How it works:**
1. Send a WhatsApp message to the SuoOps Bot
2. Just write what you sold in plain English
3. Bot creates invoice automatically
4. Customer gets payment link instantly

**Example Messages:**
```
"Invoice Jane 50,000 naira for logo design"

"Create invoice for John Smith, 75000 for website development"

"Bill Mary 25k for social media package"
```

**What happens:**
- ✅ Bot understands your message
- ✅ Extracts: customer name, amount, description
- ✅ Creates professional invoice with your branding
- ✅ Sends payment link to customer
- ✅ You get notification when paid

**Time:** ~5 seconds

---

### 2️⃣ WhatsApp Voice Note (Hands-Free)

**How it works:**
1. Open WhatsApp, tap microphone
2. Say what you sold (like talking to a friend)
3. Send voice note to SuoOps Bot
4. Invoice created from your voice

**Example Voice Notes:**
```
"Hey, invoice Jane fifty thousand naira for logo design"

"Create invoice for John, seventy-five thousand for website"

"Bill Mary twenty-five k for social media package"
```

**What happens:**
- ✅ OpenAI Whisper transcribes your voice (converts to text)
- ✅ Bot understands Nigerian English (e.g., "fifty k" = 50,000)
- ✅ Creates invoice automatically
- ✅ Customer receives payment link

**Time:** ~10 seconds  
**Cost:** ~₦5 per voice note  
**Best for:** Busy entrepreneurs, on-the-go invoicing

---

### 3️⃣ Photo/Receipt Upload (OCR)

**How it works:**
1. Take photo of receipt or handwritten note
2. Upload via API or dashboard
3. AI reads the image and extracts data
4. Invoice created from photo

**What you can photograph:**
- ✅ Store receipts
- ✅ Handwritten notes
- ✅ Printed invoices
- ✅ Purchase orders
- ✅ Delivery notes

**Example:**
```
Customer buys items from your store
↓
You write receipt: "Jane - Rice ₦5000, Oil ₦3000"
↓
Take photo with phone
↓
Upload to SuoOps
↓
Invoice created: Total ₦8000, items listed
```

**What happens:**
- ✅ OpenAI Vision (GPT-4o) reads the image
- ✅ Extracts: customer name, items, prices, total
- ✅ Understands Nigerian currency and formats
- ✅ Creates structured invoice
- ✅ You review before sending (optional)

**Time:** ~8 seconds  
**Cost:** ~₦20 per image  
**Accuracy:** 85-95% for clear images  
**Best for:** Physical stores, market traders, receipts

---

### 4️⃣ QR Code Verification (Customer Payment)

**How it works:**
1. You create invoice (via WhatsApp/voice/photo)
2. Customer receives payment link
3. Customer pays via Paystack
4. Customer gets invoice with QR code
5. **You scan QR code to verify payment instantly**

**The Customer Journey:**
```
Receives invoice → Clicks "Pay Now" → Enters card details
→ Pays → Gets receipt with QR code
```

**The Business Owner Journey (You):**
```
Customer shows phone with receipt → You scan QR code
→ Instant verification: ✅ PAID or ❌ UNPAID
→ Deliver product/service confidently
```

**What QR Code Contains:**
- Invoice ID
- Payment status (PAID/PENDING/FAILED)
- Customer name
- Amount paid
- Payment date/time
- Transaction reference

**Why It's Important:**
- ❌ **Problem:** Customer shows fake screenshot saying "I paid"
- ✅ **Solution:** Scan QR code, see real payment status from Paystack
- 🔒 **Security:** QR code is cryptographically signed, can't be faked
- ⚡ **Speed:** Know payment status in 2 seconds

**How to Scan:**
1. Customer shows their phone (receipt on screen)
2. You open SuoOps dashboard or WhatsApp
3. Point camera at QR code
4. See instant verification: PAID ✅ or UNPAID ❌
5. Deliver product/service only if PAID

**Best for:** In-person deliveries, market sales, preventing fraud

---

## 🔄 Complete User Flow (All Features Together)

### Scenario: You sell a logo design to Jane for ₦50,000

```
STEP 1: CREATE INVOICE (Choose any method)
├─ Option A: WhatsApp text → "Invoice Jane 50k for logo"
├─ Option B: Voice note → "Hey, bill Jane fifty thousand for logo"  
├─ Option C: Photo receipt → Snap handwritten note
└─ Option D: Dashboard → Fill form manually

↓

STEP 2: INVOICE CREATED (Automatic - 5-10 seconds)
├─ Professional PDF generated with your logo
├─ Payment link created (Paystack)
├─ Email sent to Jane (if you have her email)
└─ WhatsApp notification (if you have her number)

↓

STEP 3: CUSTOMER PAYS (Jane's side)
├─ Jane clicks "Pay Now" button
├─ Enters card details on Paystack
├─ Pays ₦50,000
└─ Gets receipt with QR code

↓

STEP 4: YOU GET NOTIFIED (Real-time)
├─ WhatsApp: "Jane paid ₦50,000 ✅"
├─ Email: Payment confirmation
└─ Dashboard: Invoice status → PAID

↓

STEP 5: VERIFICATION (When delivering)
├─ Jane shows receipt on her phone
├─ You scan QR code with your phone
├─ See: ✅ PAID - ₦50,000 - Oct 30, 2025
└─ Deliver logo files confidently

↓

STEP 6: DONE! 🎉
├─ Jane has her logo
├─ You have your money
└─ Both have proof of transaction
```

---

## 🧠 How the AI Works (Behind the Scenes)

### Voice Notes → Invoice
1. **You speak:** "Invoice Jane fifty thousand naira for logo design"
2. **Whisper AI:** Converts voice to text (speech-to-text)
3. **NLP Service:** Understands the text:
   - Customer name: "Jane"
   - Amount: "fifty thousand" → ₦50,000
   - Description: "logo design"
4. **Invoice Service:** Creates professional invoice
5. **Done:** Jane gets payment link

### Photos → Invoice
1. **You upload:** Photo of receipt showing items and prices
2. **GPT-4o Vision:** "Reads" the image like a human:
   - Sees: "Rice - ₦5000, Oil - ₦3000"
   - Understands: 2 items, total ₦8000
   - Extracts: Customer name (if visible)
3. **OCR Service:** Structures the data:
   ```json
   {
     "items": [
       {"description": "Rice", "price": 5000},
       {"description": "Oil", "price": 3000}
     ],
     "total": 8000
   }
   ```
4. **Invoice Service:** Creates invoice
5. **Done:** You review and send

### QR Code → Verification
1. **Customer pays:** Paystack processes payment
2. **Receipt generated:** PDF with embedded QR code
3. **QR code contains:** Encrypted invoice data + payment proof
4. **You scan:** Camera reads QR code
5. **Verification:** Your app checks with Paystack:
   - "Is invoice INV-123 paid?"
   - Paystack replies: "Yes, paid ₦50,000 at 2:30pm"
6. **Display:** ✅ PAID or ❌ UNPAID on your screen

---

## 💰 Cost Breakdown

| Feature | Cost per Use | When Charged |
|---------|--------------|--------------|
| WhatsApp Text | FREE | Never |
| WhatsApp Voice | ~₦5 | Per voice note |
| Photo OCR | ~₦20 | Per image uploaded |
| QR Verification | FREE | Never |
| Invoice Creation | FREE | Never |
| Payment Processing | 1.5% + ₦100 | When customer pays (Paystack fee) |

**Example: ₦50,000 Invoice**
- Create via voice: ₦5
- Customer pays: ₦850 fee (1.5% + ₦100)
- You receive: ₦49,150
- QR verification: FREE

---

## 📊 Subscription Plans (Monthly)

### STARTER (FREE Forever)
- ✅ 100 invoices/month
- ✅ All 4 creation methods (text, voice, photo, manual)
- ✅ QR verification
- ✅ Basic branding (logo)
- ✅ Payment tracking
- ❌ No email sending
- ❌ No analytics

### PRO (₦5,000/month)
- ✅ 500 invoices/month
- ✅ Email invoices automatically
- ✅ Advanced analytics (graphs, reports)
- ✅ Priority support
- ✅ Custom branding (colors, fonts)
- ✅ Export to Excel/PDF

### BUSINESS (₦15,000/month)
- ✅ 2,000 invoices/month
- ✅ Multi-user (add team members)
- ✅ API access (integrate with your app)
- ✅ Automated reminders (unpaid invoices)
- ✅ Custom domains (invoices@yourbrand.com)
- ✅ WhatsApp business integration

### ENTERPRISE (₦50,000/month)
- ✅ Unlimited invoices
- ✅ Everything in Business +
- ✅ Dedicated account manager
- ✅ Custom features
- ✅ SLA guarantees
- ✅ White-label option

---

## 🎬 Real-Life Examples

### Example 1: Market Trader (Voice)
**Situation:** You sell vegetables at Mile 12 Market, Lagos

```
Customer: "How much for tomatoes and peppers?"
You: "₦8,000 total ma"
Customer: "Okay, I'll transfer"

[While packing items, speak into phone]
You: "Invoice Mrs. Adebayo eight thousand naira 
      for tomatoes and peppers"

[5 seconds later]
Bot: "Invoice created! Payment link sent"
Customer: [Pays on phone while you pack]
Customer: "I've paid, here's my receipt"
You: [Scan QR code]
Phone: "✅ PAID - ₦8,000"
You: "Thank you ma!" [Hand over items]
```

**Total time:** 30 seconds  
**Typing:** Zero  
**Fraud risk:** Zero (QR verified)

---

### Example 2: Graphic Designer (Photo)
**Situation:** Client shows you handwritten quote from another designer

```
Client: "Can you match this price?"
You: [Look at paper - Rice logo ₦40k, Business card ₦15k]
You: "Yes, I can do ₦50k total"

[Take photo of the quote with your phone]
[Upload to SuoOps]

[8 seconds later - OCR extracts data]
You: [Review] "Logo - ₦40k, Business card - ₦15k, Total ₦55k"
You: [Adjust total to ₦50k as agreed]
You: [Click "Send Invoice"]

Client: [Gets email with payment link]
Client: [Pays immediately]
You: [Start working on designs]
```

**Total time:** 1 minute  
**Manual data entry:** Zero  
**Pricing errors:** Zero

---

### Example 3: Delivery Driver (QR Code)
**Situation:** You deliver food orders, customers sometimes lie about payment

```
OLD WAY (Before SuoOps):
Customer: "I've paid oh, see" [Shows screenshot]
You: [Can't verify, hand over food]
Customer: [Actually didn't pay - screenshot was edited]
You: [Lost money 😢]

NEW WAY (With SuoOps):
Customer: "I've paid, see" [Shows screenshot]
You: "Let me scan the QR code"
[Scan shows: ❌ UNPAID]
You: "Please pay now, it's showing unpaid"
Customer: [Caught, pays for real]
You: [Scan again: ✅ PAID]
You: [Hand over food] ✅
```

**Fraud prevented:** 100%  
**Peace of mind:** Priceless

---

## 🔐 Security & Privacy

### How We Keep Your Data Safe

1. **QR Codes are Cryptographically Signed**
   - Can't be faked or edited
   - Contains encrypted payment proof
   - Verified against Paystack in real-time

2. **Payment Data Never Stored**
   - Card details go directly to Paystack (PCI-DSS certified)
   - We only know: "Invoice paid" or "not paid"
   - Your money goes straight to your bank

3. **Voice/Photo Data is Temporary**
   - Voice notes transcribed, then deleted
   - Photos processed, data extracted, then deleted
   - Only invoice details kept (no raw files)

4. **WhatsApp is End-to-End Encrypted**
   - Messages between you and bot are private
   - We only see what you choose to send

5. **Your OpenAI API Key**
   - Stored securely on Heroku (encrypted)
   - Only used for your account
   - Never shared or logged

---

## 🚀 Getting Started (5 Minutes)

### Step 1: Sign Up (2 minutes)
1. Go to https://suoops.com
2. Click "Get Started"
3. Enter phone number
4. Verify OTP code
5. Add business name

### Step 2: Add Business Details (2 minutes)
1. Go to Settings
2. Upload logo (optional but recommended)
3. Add bank account (for receiving payments)
4. Save

### Step 3: Create First Invoice (1 minute)
**Option A: WhatsApp**
1. Save SuoOps Bot number
2. Send: "Invoice Test Customer 1000 for test item"
3. Done! ✅

**Option B: Dashboard**
1. Click "New Invoice"
2. Fill: Name, Amount, Description
3. Click "Create"
4. Done! ✅

### Step 4: Test Payment
1. Use your own phone number as customer
2. Click payment link you received
3. Pay ₦1,000 (test with your card)
4. Get receipt with QR code
5. Scan QR code to verify
6. Success! 🎉

---

## 🆘 Common Questions

### "Do I need WhatsApp Business?"
**No.** Regular WhatsApp works perfectly.

### "Can customers pay without internet?"
**No.** They need internet to access Paystack payment page. But QR verification works offline (you just need to scan once while online).

### "What if customer says photo is blurry?"
They can request new invoice via email. Or you can resend from dashboard.

### "How accurate is voice recognition?"
85-95% for clear audio. Works with Nigerian English accent. Understands "fifty k", "naira", etc.

### "Can I use this for international customers?"
Yes! Supports USD, GBP, EUR. Paystack handles currency conversion.

### "What if I don't have a logo?"
Invoice still works! It just uses your business name as text. You can add logo later.

### "Is there a daily limit?"
- FREE plan: 100 invoices/month (~3/day)
- PRO plan: 500/month (~16/day)
- No daily limit, only monthly

### "Can customers pay cash?"
Yes! You can mark invoice as "Paid - Cash" manually. QR code verification is only for online payments.

---

## 📞 Support

- **Email:** support@suoops.com
- **WhatsApp:** [SuoOps Bot number]
- **Dashboard:** Help button (bottom right)
- **Response time:** 24 hours (PRO+), 48 hours (FREE)

---

## 🎯 Best Practices

### ✅ DO:
- Keep phone number updated (for OTP codes)
- Test QR verification before trusting customers
- Upload clear, well-lit photos (for OCR)
- Speak clearly in voice notes (reduce background noise)
- Review OCR extracts before sending (check amounts)
- Add customer phone/email for auto-notifications

### ❌ DON'T:
- Share your login with untrusted people
- Accept screenshots as payment proof (use QR)
- Upload sensitive documents (only receipts/invoices)
- Rely on voice notes in very noisy environments
- Forget to check payment status before delivery

---

## 🎊 Summary

**SuoOps makes invoicing as simple as:**

1. **Say it** (voice note) → Invoice created
2. **Type it** (WhatsApp) → Invoice created
3. **Snap it** (photo) → Invoice created
4. **Scan it** (QR code) → Payment verified

**No more:**
- ❌ Typing customer details
- ❌ Calculating totals
- ❌ Designing invoices
- ❌ Trusting payment screenshots
- ❌ Manual record-keeping

**Just:**
- ✅ Tell us what you sold
- ✅ We handle everything
- ✅ Get paid safely
- ✅ Verify instantly

---

**Ready to try?** → https://suoops.com

**Questions?** → support@suoops.com

---

*Made with ❤️ for Nigerian entrepreneurs*
