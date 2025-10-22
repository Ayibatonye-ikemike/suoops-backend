# SuoPay Unit Cost Breakdown 💰

**Last Updated:** October 22, 2025  
**Currency:** Nigerian Naira (₦)

---

## 📊 Cost Per Invoice

### Text Invoice (Standard Flow)

| Component | Cost | Details |
|-----------|------|---------|
| **WhatsApp Message (Notification)** | ₦0 - ₦3 | Free for first 1,000/month, then ₦3 each |
| **Database Operations** | ₦0.001 | 3 writes: invoice + line items + audit log |
| **PDF Generation (CPU/Memory)** | ₦0.01 | ReportLab rendering ~0.2 seconds |
| **S3 Storage (Upload + Store)** | ₦0.05 | Upload fee + 1 month storage |
| **API Request Processing** | ₦0 | Included in Heroku dyno cost |
| **TOTAL PER TEXT INVOICE** | **₦3.06** | **Your actual cost** |

**Breakdown:**
```
First 1,000 invoices/month: ₦0.06 each (within WhatsApp free tier)
After 1,000 invoices/month: ₦3.06 each (WhatsApp ₦3 + ₦0.06)
```

---

### Voice Invoice (WhatsApp Voice Note)

| Component | Cost | Details |
|-----------|------|---------|
| **Voice Note Download** | ₦0 | Free via WhatsApp Media API |
| **OpenAI Whisper Transcription** | ₦2.44 - ₦9.75 | Depends on audio length |
| **Standard Invoice Creation** | ₦3.06 | Same as text invoice above |
| **TOTAL PER VOICE INVOICE** | **₦5.50 - ₦12.81** | **Your actual cost** |

**Transcription Cost by Audio Length:**
| Audio Length | OpenAI Cost (USD) | Naira Cost @ ₦1,625/$1 |
|--------------|-------------------|------------------------|
| 15 seconds | $0.0015 | ₦2.44 |
| 30 seconds | $0.003 | ₦4.88 |
| 45 seconds | $0.0045 | ₦7.31 |
| 60 seconds | $0.006 | ₦9.75 |

**Total Voice Invoice Cost:**
```
15s voice note: ₦2.44 + ₦3.06 = ₦5.50
30s voice note: ₦4.88 + ₦3.06 = ₦7.94 (average)
45s voice note: ₦7.31 + ₦3.06 = ₦10.37
60s voice note: ₦9.75 + ₦3.06 = ₦12.81
```

---

## 📊 Cost Per Payroll Run

### Single Payroll Run (10 Workers)

| Component | Cost | Details |
|-----------|------|---------|
| **PDF Generation (10 Payslips)** | ₦0.10 | 10 workers × ₦0.01 per PDF |
| **S3 Storage (10 Payslips)** | ₦0.50 | 10 workers × ₦0.05 per file |
| **WhatsApp Notifications (10)** | ₦0 - ₦30 | Free for first 1,000/month total |
| **Database Operations** | ₦0.01 | PayrollRun + 10 PayrollRecords |
| **API Request Processing** | ₦0 | Included in Heroku dyno cost |
| **TOTAL PER PAYROLL RUN** | **₦0.61 - ₦30.61** | **Your actual cost** |

**Breakdown:**
```
First 100 payroll runs/month: ₦0.61 each (within WhatsApp free tier)
After 100 payroll runs/month: ₦30.61 each (WhatsApp ₦30 + ₦0.61)
```

---

### Cost Per Worker in Payroll

| Workers | Cost Per Run | Cost Per Worker |
|---------|--------------|-----------------|
| 1 worker | ₦0.06 - ₦3.06 | ₦0.06 - ₦3.06 |
| 10 workers | ₦0.61 - ₦30.61 | ₦0.061 - ₦3.061 |
| 50 workers | ₦3.06 - ₦153.06 | ₦0.061 - ₦3.061 |
| 100 workers | ₦6.11 - ₦306.11 | ₦0.061 - ₦3.061 |

**Pattern:** Cost per worker remains constant at **₦0.061 - ₦3.061** regardless of scale.

---

## 📊 Cost Per Customer (Monthly)

### Small Customer (10 invoices/month)

| Item | Calculation | Cost |
|------|-------------|------|
| Text Invoices | 10 × ₦0.06 | ₦0.60 |
| Voice Invoices | 0 × ₦7.94 | ₦0 |
| WhatsApp | Within free tier | ₦0 |
| **Total Variable Cost** | | **₦0.60** |
| **Your Revenue (Free Plan)** | | **₦0** |
| **Loss Per Customer** | | **-₦0.60** |

---

### Medium Customer (100 invoices/month)

| Item | Calculation | Cost |
|------|-------------|------|
| Text Invoices | 80 × ₦3.06 | ₦244.80 |
| Voice Invoices | 20 × ₦7.94 | ₦158.80 |
| WhatsApp | 100 messages (paid) | ₦0 |
| **Total Variable Cost** | | **₦403.60** |
| **Your Revenue (Pro @ ₦5,000)** | | **₦5,000** |
| **Profit Per Customer** | | **₦4,596.40** |
| **Profit Margin** | | **91.9%** |

---

### Large Customer (1,000 invoices/month)

| Item | Calculation | Cost |
|------|-------------|------|
| Text Invoices | 800 × ₦3.06 | ₦2,448 |
| Voice Invoices | 200 × ₦7.94 | ₦1,588 |
| WhatsApp | 1,000 messages (paid) | ₦0 |
| **Total Variable Cost** | | **₦4,036** |
| **Your Revenue (Pro @ ₦5,000)** | | **₦5,000** |
| **Profit Per Customer** | | **₦964** |
| **Profit Margin** | | **19.3%** |

**Note:** Large customers should be on Enterprise tier (₦20,000) for better margins!

---

### Payroll Customer (100 workers, 4 runs/month)

| Item | Calculation | Cost |
|------|-------------|------|
| Payroll Runs | 4 × ₦30.61 | ₦122.44 |
| Worker Notifications | 400 × ₦3 | ₦1,200 |
| **Total Variable Cost** | | **₦1,322.44** |
| **Your Revenue (Enterprise @ ₦20,000)** | | **₦20,000** |
| **Profit Per Customer** | | **₦18,677.56** |
| **Profit Margin** | | **93.4%** |

---

## 🎯 Marginal Cost Analysis

### What Happens When You Add 1 More...

#### 1 More Text Invoice
- **Cost:** ₦3.06 (after free WhatsApp tier)
- **Revenue Impact:** ₦0 (subscription already paid)
- **Marginal Profit:** -₦3.06

#### 1 More Voice Invoice
- **Cost:** ₦7.94 (30s average)
- **Revenue Impact:** ₦0 (subscription already paid)
- **Marginal Profit:** -₦7.94

#### 1 More Customer (Pro)
- **Cost:** ₦403.60 (assuming 100 invoices)
- **Revenue:** ₦5,000
- **Marginal Profit:** ₦4,596.40

#### 1 More Worker in Payroll
- **Cost:** ₦3.06 per run (₦12.24/month for 4 runs)
- **Revenue Impact:** ₦0 (Enterprise already paid)
- **Marginal Profit:** -₦12.24

---

## 📈 Cost Scaling Examples

### 100 Customers Scenario

| Customer Mix | Count | Invoices Each | Cost Per | Total Cost | Revenue | Profit |
|--------------|-------|---------------|----------|------------|---------|--------|
| **Free** | 50 | 10 | ₦0.60 | ₦30 | ₦0 | -₦30 |
| **Pro** | 40 | 100 | ₦403.60 | ₦16,144 | ₦200,000 | ₦183,856 |
| **Enterprise** | 10 | 50 | ₦1,322.44 | ₦13,224 | ₦200,000 | ₦186,776 |
| **Total** | **100** | | | **₦29,398** | **₦400,000** | **₦370,602** |

**Plus Infrastructure:** ₦78,325/month  
**Net Profit:** ₦370,602 - ₦78,325 = **₦292,277/month**  
**Profit Margin:** 73%

---

### 1,000 Customers Scenario

| Customer Mix | Count | Invoices Each | Cost Per | Total Cost | Revenue | Profit |
|--------------|-------|---------------|----------|------------|---------|--------|
| **Free** | 500 | 10 | ₦0.60 | ₦300 | ₦0 | -₦300 |
| **Pro** | 400 | 100 | ₦403.60 | ₦161,440 | ₦2,000,000 | ₦1,838,560 |
| **Enterprise** | 100 | 50 | ₦1,322.44 | ₦132,244 | ₦2,000,000 | ₦1,867,756 |
| **Total** | **1,000** | | | **₦293,984** | **₦4,000,000** | **₦3,706,016** |

**Plus Infrastructure:** ₦78,325/month (need to upgrade soon)  
**Net Profit:** ₦3,706,016 - ₦78,325 = **₦3,627,691/month**  
**Profit Margin:** 90.7%

---

## 💡 Cost Optimization Insights

### Invoice Costs

1. **Encourage Text Over Voice**
   - Text: ₦3.06 per invoice
   - Voice: ₦7.94 per invoice
   - **Savings: ₦4.88 per invoice (61% cheaper)**

2. **Batch WhatsApp Notifications**
   - Send daily summaries instead of real-time
   - Reduces messages from 1,000 to ~30/month
   - **Savings: ~₦2,910/month per customer**

3. **Implement Voice Note Length Limits**
   - Limit to 30 seconds (₦4.88) instead of 60s (₦9.75)
   - **Savings: ₦4.87 per voice invoice (50% cheaper)**

4. **Cache PDF Templates**
   - Reuse rendered templates
   - Reduces CPU time by 40%
   - **Savings: ₦0.004 per invoice (negligible)**

### Payroll Costs

1. **Weekly vs Daily Payroll**
   - Daily: 30 runs × ₦30.61 = ₦918.30
   - Weekly: 4 runs × ₦30.61 = ₦122.44
   - **Savings: ₦795.86/month (87% cheaper)**

2. **Batch Worker Notifications**
   - Send payslip via email instead of WhatsApp
   - Eliminates ₦3/worker cost
   - **Savings: ₦300 per 100-worker payroll**

3. **PDF Compression**
   - Compress payslips before S3 upload
   - Reduces storage by 60%
   - **Savings: ₦0.03 per worker (60% cheaper storage)**

---

## 🎯 Pricing Strategy Implications

### Recommended Pricing Based on Costs

#### Invoice Product

| Plan | Price | Max Invoices | Variable Cost @ Max | Margin |
|------|-------|--------------|---------------------|--------|
| **Free** | ₦0 | 10 | ₦0.60 | Loss leader |
| **Pro** | ₦5,000 | 500 | ₦1,530 | 69.4% |
| **Enterprise** | ₦20,000 | Unlimited | ₦4,036 @ 1,000 | 79.8% |

**Insight:** Even at 1,000 invoices (₦4,036 cost), Enterprise plan (₦20,000) still has 79.8% margin!

#### Payroll Product

| Plan | Price | Max Workers | Variable Cost @ Max | Margin |
|------|-------|-------------|---------------------|--------|
| **Pro** | ₦5,000 | 10 | ₦122.44 | 97.6% |
| **Enterprise** | ₦20,000 | 100 | ₦1,322.44 | 93.4% |

**Insight:** Payroll has much better margins (93-97%) than invoicing!

---

## 📊 Cost Per Feature

| Feature | Cost Per Use | Monthly @ 100 Uses | Notes |
|---------|--------------|-------------------|-------|
| **Text Invoice** | ₦3.06 | ₦306 | Standard flow |
| **Voice Invoice** | ₦7.94 | ₦794 | 30s average |
| **Invoice View** | ₦0.0001 | ₦0.01 | S3 GET request |
| **PDF Download** | ₦0.0002 | ₦0.02 | S3 bandwidth |
| **WhatsApp Message** | ₦0-3 | ₦0-300 | Free tier first 1k |
| **Payment Link** | ₦0 | ₦0 | Paystack handles free |
| **Webhook Processing** | ₦0.0001 | ₦0.01 | Database write |
| **Payroll Run (10)** | ₦30.61 | ₦3,061 | With WhatsApp |
| **Payslip Generation** | ₦0.06 | ₦6 | Per worker |

---

## 🚨 Cost Alerts & Thresholds

### When to Worry About Costs

#### Voice Transcription
- **Green:** < ₦10,000/month (< 2,000 voice notes)
- **Yellow:** ₦10,000-50,000/month (2,000-10,000 voice notes)
- **Red:** > ₦50,000/month (> 10,000 voice notes)

**Action:** If hitting Red, consider limiting voice note length or encouraging text.

#### WhatsApp Messages
- **Green:** < 1,000 messages/month (free tier)
- **Yellow:** 1,000-10,000 messages/month (₦8,000-80,000)
- **Red:** > 10,000 messages/month (> ₦80,000)

**Action:** If hitting Red, implement batch notifications or email alternatives.

#### S3 Storage
- **Green:** < 10GB (< ₦230/month)
- **Yellow:** 10-50GB (₦230-1,150/month)
- **Red:** > 50GB (> ₦1,150/month)

**Action:** If hitting Red, implement PDF compression or cleanup old invoices.

---

## 💰 Final Unit Cost Summary

### Absolute Minimum Costs (Best Case)
- **Text Invoice:** ₦0.06 (within WhatsApp free tier)
- **Voice Invoice:** ₦2.50 (15s audio + free WhatsApp)
- **Payroll (10 workers):** ₦0.61 (within free tier)

### Typical Costs (After Free Tier)
- **Text Invoice:** ₦3.06
- **Voice Invoice:** ₦7.94 (30s average)
- **Payroll (10 workers):** ₦30.61

### Maximum Costs (Worst Case)
- **Text Invoice:** ₦3.06 (same as typical)
- **Voice Invoice:** ₦12.81 (60s audio)
- **Payroll (100 workers):** ₦306.11

---

**Key Takeaway:** Your marginal costs are extremely low. The business model is highly scalable with profit margins of 70-97% after covering fixed infrastructure costs! 🚀

---

**Last Updated:** October 22, 2025  
**Next Review:** Track actual usage patterns after first 100 customers
