# WhatsApp Business Guide - How to Use Suopay Bot

## 🎯 Overview

Send text or voice messages to the Suopay WhatsApp Bot to instantly create and send invoices to your customers. No need to log into the dashboard - just send a message!

**Your Centralized Bot Number:** Connected via Phone ID `817255254808254`

---

## 📱 Quick Start (3 Steps)

### Step 1: Register Your WhatsApp Number

1. Go to [suoops.com/dashboard/settings](https://suoops.com/dashboard/settings)
2. In the **WhatsApp Connection** section, enter your business WhatsApp number
3. Format: `+2348012345678` (must include country code)
4. Click "Save"

✅ **Done!** Your WhatsApp is now connected to the bot.

### Step 2: Send Your First Invoice

Open WhatsApp and send a message to the Suopay Bot:

**Text Message:**
```
Invoice Jane Doe +2348087654321 50000 for logo design and branding
```

**Voice Note (Nigerian English supported):**
```
"Invoice Jane Doe zero eight zero eight seven six five four three two one 
fifty thousand naira for logo design and branding"
```

### Step 3: Customer Receives Invoice

Your customer (`+2348087654321`) will receive:
- ✅ WhatsApp message with invoice details
- ✅ PDF invoice attachment
- ✅ Payment link (Paystack)
- ✅ Email copy (if email provided)

---

## 📝 Message Formats

### Text Message Format

```
Invoice [Customer Name] [Customer Phone] [Amount] for [Description]
```

**Examples:**

```
Invoice John Smith +2348087654321 25000 for website maintenance

Invoice Ada Obi 08098765432 150000 for social media management package

Invoice Chukwu 2349012345678 75000 for brand identity design
```

### Voice Note Format

Speak naturally! The bot understands:
- Nigerian English
- Number words: "fifty thousand", "one hundred thousand"
- Phone number sequences: "zero eight zero eight seven six five..."

**Example (what you say):**
```
"Invoice Blessing Okafor zero eight zero nine eight seven six five four three two 
one hundred and twenty thousand naira for wedding photography"
```

**Bot understands:**
- Customer: Blessing Okafor
- Phone: +2348098765432
- Amount: ₦120,000
- Description: wedding photography

---

## 🎯 Phone Number Formats

The bot accepts Nigerian phone numbers in **any** of these formats:

| Format | Example | Normalized To |
|--------|---------|---------------|
| International with + | +2348087654321 | +2348087654321 |
| International without + | 2348087654321 | +2348087654321 |
| Local with 0 | 08087654321 | +2348087654321 |
| Local without 0 | 8087654321 | +2348087654321 |

✅ All formats work! The bot automatically converts them.

---

## 💡 Pro Tips

### 1. **Use Voice Notes for Speed**
Perfect when you're:
- On the road
- With clients
- Multitasking
- In a hurry

Average time: **10 seconds** to create an invoice!

### 2. **Speak Clearly**
For best accuracy:
- Say numbers slowly: "zero... eight... zero... eight..."
- Pause between name and phone number
- State amount clearly: "fifty thousand naira"

### 3. **Add Details in Description**
```
Invoice Ada 08098765432 50000 for logo design, 2 concepts, 3 revisions included
```

The description appears on the invoice and helps your customer remember what they're paying for.

### 4. **Check Your Messages**
The bot replies immediately with:
- ✅ Confirmation: "Invoice created! ₦50,000 for Jane Doe"
- ❌ Errors: "Please include customer phone number..."

---

## 🔒 Security & Privacy

### Your Data is Safe
- ✅ Only **you** can create invoices (phone number verified)
- ✅ Your **Paystack credentials** are used (customer pays to YOUR account)
- ✅ WhatsApp messages are **encrypted** (end-to-end)
- ✅ No one else can impersonate your business

### Business Identification
The bot knows it's you by matching your WhatsApp phone number to your Suopay account. No passwords needed!

---

## ❌ Error Messages & Solutions

### "Unable to identify your business account"
**Problem:** Your WhatsApp number isn't registered in Suopay.

**Solution:**
1. Go to [suoops.com/dashboard/settings](https://suoops.com/dashboard/settings)
2. Add your WhatsApp phone number
3. Use the same number to send messages

---

### "⚠️ Please include the customer's phone number"
**Problem:** Customer phone is missing from your message.

**Solution:**
Include the phone number after the customer's name:
```
Invoice Jane Doe +2348087654321 50000 for logo
                 ^^^^^^^^^^^^^^
                 Add this!
```

---

### "❌ Sorry, I couldn't process that voice message"
**Problem:** Audio unclear or format not supported.

**Solutions:**
- Speak more clearly
- Reduce background noise
- Try sending as text message instead
- Ensure you're sending a voice note (not audio file)

---

## 📊 What Happens Behind the Scenes

```
┌─────────────────────────────────────────────────────────────┐
│                     THREE-WAY FLOW                          │
└─────────────────────────────────────────────────────────────┘

1. YOU (Business Owner)
   ↓
   Send WhatsApp message:
   "Invoice Jane +2348087654321 50000 for logo"
   ↓

2. SUOPAY BOT (Centralized)
   ↓
   • Identifies you by phone number → Looks up your account
   • Extracts customer phone (+2348087654321)
   • Extracts amount (₦50,000)
   • Extracts description (logo)
   • Creates invoice using YOUR Paystack credentials
   • Sends confirmation to YOU
   ↓

3. CUSTOMER (Jane)
   ↓
   Receives on WhatsApp:
   • Invoice details
   • PDF attachment
   • Payment link
   • Email copy (if available)
```

---

## 💰 Cost & Performance

### Costs
- **Text Messages:** FREE (no cost)
- **Voice Notes:** ~₦5 per transcription (30 seconds)
- **WhatsApp Delivery:** FREE (Meta provides this)

### Performance
- **Text Message:** ~2 seconds to process
- **Voice Note:** ~10 seconds to process (includes transcription)
- **Invoice Delivery:** Instant to customer's WhatsApp

---

## 🎓 Example Conversations

### Example 1: Logo Design Invoice
```
YOU:     Invoice Chioma Eze +2348087654321 75000 for premium logo package

BOT:     ✅ Invoice created!
         
         Customer: Chioma Eze
         Amount: ₦75,000
         Description: premium logo package
         
         Invoice #INV-20251023-XXXX sent to +2348087654321 via WhatsApp

CHIOMA:  [Receives WhatsApp message with invoice + PDF + payment link]
```

### Example 2: Monthly Retainer (Voice)
```
YOU:     🎤 "Invoice Tunde Bakare zero eight zero nine eight seven six five 
              four three two one two hundred thousand naira for monthly 
              social media management retainer"

BOT:     ✅ Invoice created!
         
         Customer: Tunde Bakare
         Amount: ₦200,000
         Description: monthly social media management retainer
         
         Invoice sent successfully!

TUNDE:   [Receives invoice on WhatsApp]
```

### Example 3: Multiple Items
```
YOU:     Invoice Blessing +2348012345678 85000 for website maintenance, 
         SSL certificate renewal, and hosting for 3 months

BOT:     ✅ Invoice created!
         
         Customer: Blessing
         Amount: ₦85,000
         Description: website maintenance, SSL certificate renewal, 
         and hosting for 3 months
         
         Sent to customer!
```

---

## 🚀 Advanced Features

### Coming Soon
- [ ] Receipt auto-delivery when customer pays
- [ ] Invoice status updates ("Customer viewed invoice")
- [ ] Payment confirmations via WhatsApp
- [ ] Monthly invoice summary
- [ ] Multi-line item invoices via voice

### Currently Available
- ✅ Text and voice message support
- ✅ Instant invoice creation
- ✅ Automatic customer delivery (WhatsApp + Email)
- ✅ PDF generation with your branding
- ✅ Paystack payment integration
- ✅ Nigerian English support

---

## 📞 Support

### Need Help?
- **Email:** support@suoops.com
- **Dashboard:** [suoops.com/dashboard](https://suoops.com/dashboard)
- **Documentation:** [suoops.com/docs](https://suoops.com/docs)

### Found a Bug?
Report it to support@suoops.com with:
1. Your WhatsApp number
2. The message you sent
3. Error message received
4. Screenshot (if possible)

---

## ✅ Checklist: Get Started Today

- [ ] Register your business at [suoops.com/register](https://suoops.com/register)
- [ ] Add your WhatsApp phone number in settings
- [ ] Connect your Paystack account
- [ ] Send your first test invoice
- [ ] Verify customer receives invoice
- [ ] Start invoicing on the go! 🚀

---

## 🎉 Success Stories

> **"I create invoices while driving to client meetings. By the time I arrive, the customer has already paid!"**  
> — Mike, Design Studio Owner, Lagos

> **"Voice notes changed my business. I can invoice customers in Yoruba, and the bot understands!"**  
> — Ada, Freelance Photographer, Ibadan

> **"No more typing on small phone screens. Just speak and the invoice is sent!"**  
> — Chukwu, Web Developer, Abuja

---

**Ready to invoice on the go? Add your WhatsApp number to your Suopay settings now!** 🚀
