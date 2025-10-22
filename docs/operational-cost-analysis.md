# SuoPay Operational Cost Analysis 💰

**Last Updated:** October 22, 2025  
**Currency:** Nigerian Naira (₦) and USD ($)

---

## Executive Summary

### Cost Per Invoice (Standard Text)
| Component | Cost | Notes |
|-----------|------|-------|
| WhatsApp Message (Outbound) | ₦0 - ₦3 | Free for first 1,000/month via Meta Cloud API |
| Database Write | ₦0.001 | Negligible (included in hosting) |
| PDF Generation | ₦0.01 | CPU/memory overhead |
| S3 Storage (per invoice) | ₦0.05 | AWS S3 standard storage |
| Paystack Transaction Fee | **1.5% + ₦100** | On successful payment |
| **Total (excluding payment)** | **~₦3.06** | |
| **Total (with payment at ₦50,000)** | **₦853.06** | |

### Cost Per Invoice (Voice Note)
| Component | Cost | Notes |
|-----------|------|-------|
| WhatsApp Voice Download | ₦0 | Included in Meta API |
| OpenAI Whisper Transcription | ₦5 - ₦10 | $0.003-$0.006 for 30s-60s |
| Standard Invoice Creation | ₦3.06 | Same as text invoice |
| **Total (excluding payment)** | **~₦8-13** | |
| **Total (with payment at ₦50,000)** | **₦858-863** | |

### Cost Per Payroll Run (10 Workers)
| Component | Cost | Notes |
|-----------|------|-------|
| PDF Generation (10 payslips) | ₦0.10 | 10 × ₦0.01 |
| S3 Storage (10 payslips) | ₦0.50 | 10 × ₦0.05 |
| WhatsApp Notifications (10) | ₦0 - ₦30 | Free tier: 1,000/month |
| Bulk Payout Fee (Paystack) | **₦50 per worker** | Paystack bulk transfer |
| Database Operations | ₦0.01 | Negligible |
| **Total (excluding payouts)** | **₦0.61 - ₦30.61** | |
| **Total (with payouts)** | **₦500.61 - ₦530.61** | For 10 workers |

---

## 📊 Detailed Cost Breakdown

### 1. Infrastructure Costs (Monthly)

#### Heroku Backend (Production)
| Resource | Plan | Cost | Notes |
|----------|------|------|-------|
| **Dyno (Web)** | Eco | $5/month | Sleeps after 30 min inactivity |
| **Dyno (Web)** | Basic | $7/month | Never sleeps (recommended) |
| **Dyno (Worker)** | Basic | $7/month | For Celery tasks |
| **PostgreSQL** | Mini | $5/month | 1M rows, 20 connections |
| **PostgreSQL** | Basic | $9/month | 10M rows, 60 connections |
| **Redis** | Mini | $3/month | Upstash/Heroku Redis |
| **Total (Eco)** | | **$13/month** | **₦21,125** @ ₦1,625/$1 |
| **Total (Basic - Recommended)** | | **$26/month** | **₦42,250** @ ₦1,625/$1 |

#### Vercel Frontend (Production)
| Resource | Plan | Cost | Notes |
|----------|------|------|-------|
| **Hosting** | Hobby | $0/month | Free for personal projects |
| **Hosting** | Pro | $20/month | For production/commercial |
| **Bandwidth** | | $0 | 100GB free on Hobby |
| **Build Minutes** | | $0 | Unlimited on all plans |
| **Total** | | **$0-20/month** | **₦0-32,500** |

#### AWS S3 Storage
| Resource | Usage | Cost | Notes |
|----------|-------|------|-------|
| **Storage** | First 50GB | $0.023/GB/month | ~$1.15 for 50GB |
| **PUT Requests** | 1,000 uploads | $0.005 per 1,000 | ₦8.13 per 1,000 invoices |
| **GET Requests** | 10,000 downloads | $0.0004 per 1,000 | ₦6.50 per 10,000 views |
| **Total (1,000 invoices/month)** | | **~$1.20/month** | **₦1,950** |

#### Domain & DNS
| Resource | Plan | Cost | Notes |
|----------|------|------|-------|
| **Domain** | suopay.io | $12/year | GoDaddy/Namecheap |
| **DNS** | Vercel | $0/month | Free with Vercel nameservers |
| **SSL Certificate** | Let's Encrypt | $0/month | Free via Heroku ACM |
| **Total** | | **$1/month** | **₦1,625** |

**Total Infrastructure:** ₦45,825 - ₦78,325/month (depending on plan)

---

### 2. Per-Transaction Costs

#### WhatsApp Cloud API (Meta)
| Metric | Free Tier | Paid Rate | Notes |
|--------|-----------|-----------|-------|
| **Text Messages** | 1,000/month free | $0.005-0.01/msg | ₦8-16 per message |
| **Media Messages** | Included | $0.02-0.03/msg | ₦32-48 per message |
| **Voice Downloads** | Included | $0 | Free media downloads |
| **Template Messages** | 1,000/month free | $0.01-0.05/msg | ₦16-81 per message |

**Calculation for 5,000 invoices/month:**
- First 1,000 messages: ₦0 (free)
- Next 4,000 messages: 4,000 × ₦8 = **₦32,000**
- **Total:** ₦32,000/month

#### OpenAI Whisper API (Voice Transcription)
| Audio Length | API Cost | Naira Cost | Notes |
|--------------|----------|------------|-------|
| **15 seconds** | $0.0015 | ₦2.44 | Quick voice note |
| **30 seconds** | $0.003 | ₦4.88 | Average voice note |
| **60 seconds** | $0.006 | ₦9.75 | Long voice note |
| **Per minute** | $0.006 | ₦9.75 | Pricing unit |

**Calculation for 500 voice invoices/month (30s avg):**
- 500 × ₦4.88 = **₦2,440/month**

#### Paystack Payment Processing
| Transaction Type | Fee Structure | Example (₦50,000) |
|------------------|---------------|-------------------|
| **Local Card** | 1.5% + ₦100 | ₦850 |
| **Bank Transfer** | ₦50 flat | ₦50 |
| **USSD** | 1% capped at ₦2,000 | ₦500 |
| **International Card** | 3.9% + ₦100 | ₦2,050 |

**Revenue Share:**
- Business receives: ₦50,000 - ₦850 = **₦49,150**
- Paystack takes: **₦850** (1.7% effective rate)
- Your platform cost: **₦0** (passed to customer)

**Monthly (1,000 invoices at ₦50,000 avg):**
- Total GMV: ₦50,000,000
- Paystack fees: ₦850,000
- **Net to businesses: ₦49,150,000**

#### Paystack Bulk Payouts (Payroll)
| Payout Type | Fee | Example (₦100,000 salary) |
|-------------|-----|---------------------------|
| **Bank Transfer** | ₦50 per recipient | ₦50 |
| **Failed Transfer** | ₦0 | Free retry |
| **Reversal** | ₦0 | No fee |

**Calculation for 100 workers/month:**
- 100 × ₦50 = **₦5,000/month**

---

### 3. Cost Per Use Case

#### Scenario 1: Small Business (50 invoices/month)
| Cost Item | Amount | Notes |
|-----------|--------|-------|
| Infrastructure | ₦45,825 | Heroku Eco + Free Vercel |
| WhatsApp Messages | ₦0 | Within free tier (1,000/month) |
| S3 Storage | ₦98 | 50 invoices × ₦1.95 |
| Voice Transcription | ₦0 | No voice invoices |
| **Total Monthly** | **₦45,923** | |
| **Cost Per Invoice** | **₦918.46** | Mostly fixed costs |

#### Scenario 2: Medium Business (500 invoices/month)
| Cost Item | Amount | Notes |
|-----------|--------|-------|
| Infrastructure | ₦78,325 | Heroku Basic + Vercel Pro |
| WhatsApp Messages | ₦0 | Within free tier |
| S3 Storage | ₦975 | 500 invoices × ₦1.95 |
| Voice Transcription | ₦2,440 | 100 voice invoices |
| **Total Monthly** | **₦81,740** | |
| **Cost Per Invoice** | **₦163.48** | Economics improve |

#### Scenario 3: Large Business (5,000 invoices/month)
| Cost Item | Amount | Notes |
|-----------|--------|-------|
| Infrastructure | ₦78,325 | Same as medium |
| WhatsApp Messages | ₦32,000 | 4,000 paid messages |
| S3 Storage | ₦9,750 | 5,000 invoices × ₦1.95 |
| Voice Transcription | ₦12,200 | 500 voice invoices |
| **Total Monthly** | **₦132,275** | |
| **Cost Per Invoice** | **₦26.46** | Strong unit economics |

#### Scenario 4: Payroll Business (100 workers, 20 payrolls/month)
| Cost Item | Amount | Notes |
|-----------|--------|-------|
| Infrastructure | ₦78,325 | Same |
| WhatsApp Messages | ₦0 | 2,000 within free tier |
| S3 Storage | ₦3,900 | 2,000 payslips × ₦1.95 |
| Bulk Payout Fees | ₦100,000 | 100 × ₦50 × 20 payrolls |
| **Total Monthly** | **₦182,225** | |
| **Cost Per Payroll Run** | **₦9,111** | |
| **Cost Per Worker/Month** | **₦1,822** | Divided by 100 workers |

---

## 💡 Profitability Analysis

### Subscription Pricing (Planned)

| Plan | Price | Max Usage | Margin Analysis |
|------|-------|-----------|-----------------|
| **Free** | ₦0/month | 10 invoices | Loss: ₦46,000/user (subsidized) |
| **Pro** | ₦5,000/month | Unlimited invoices | Profitable at 200+ invoices |
| **Enterprise** | ₦20,000/month | Unlimited + Payroll | Profitable at 50+ payroll runs |

### Break-Even Analysis

#### Invoice Business
**Fixed Costs:** ₦78,325/month (infrastructure)  
**Variable Costs:** ₦13/invoice (with voice), ₦3/invoice (text only)

**Break-even calculation (Pro plan at ₦5,000):**
- Need: ₦78,325 ÷ ₦5,000 = **16 paying customers**
- At 500 invoices each = 8,000 total invoices
- Variable costs: 8,000 × ₦13 = ₦104,000
- **Total revenue needed:** ₦104,000 + ₦78,325 = ₦182,325
- **Customers needed:** 182,325 ÷ 5,000 = **37 Pro customers**

#### Payroll Business
**Fixed Costs:** ₦78,325/month  
**Variable Costs:** ₦530/payroll run (10 workers)

**Break-even calculation (Enterprise plan at ₦20,000):**
- Need: ₦78,325 ÷ ₦20,000 = **4 Enterprise customers**
- At 20 payroll runs/month each = 80 runs
- Variable costs: 80 × ₦530 = ₦42,400
- **Total revenue needed:** ₦42,400 + ₦78,325 = ₦120,725
- **Customers needed:** 120,725 ÷ 20,000 = **7 Enterprise customers**

### Revenue Projections

#### Year 1 (Conservative)
| Segment | Customers | Revenue/Month | Annual Revenue |
|---------|-----------|---------------|----------------|
| Free | 100 | ₦0 | ₦0 |
| Pro | 20 | ₦100,000 | ₦1,200,000 |
| Enterprise | 5 | ₦100,000 | ₦1,200,000 |
| **Total** | **125** | **₦200,000** | **₦2,400,000** |
| **Costs** | | ₦78,325 + ₦50,000 | ₦1,539,900 |
| **Profit** | | **₦71,675/month** | **₦860,100/year** |

#### Year 2 (Growth)
| Segment | Customers | Revenue/Month | Annual Revenue |
|---------|-----------|---------------|----------------|
| Free | 500 | ₦0 | ₦0 |
| Pro | 100 | ₦500,000 | ₦6,000,000 |
| Enterprise | 25 | ₦500,000 | ₦6,000,000 |
| **Total** | **625** | **₦1,000,000** | **₦12,000,000** |
| **Costs** | | ₦200,000 | ₦2,400,000 |
| **Profit** | | **₦800,000/month** | **₦9,600,000/year** |

---

## 🎯 Cost Optimization Strategies

### 1. Infrastructure Optimization
- **Use Heroku Eco dynos** until you hit 50 users (saves ₦32,425/month)
- **Compress PDFs** before S3 upload (save 30-50% storage)
- **Cache frequently accessed invoices** in Redis (reduce S3 GET costs)
- **Use CloudFlare CDN** for static assets (free tier)

### 2. WhatsApp Cost Reduction
- **Batch notifications** instead of sending immediately
- **Use template messages** for common responses (cheaper)
- **Implement retry logic** to avoid duplicate sends
- **Consider WhatsApp Business API** alternatives for high volume

### 3. Voice Bot Optimization
- **Limit voice note length** to 45 seconds (users get concise)
- **Implement caching** for common phrases
- **Batch transcriptions** if acceptable delay
- **Consider local transcription** for Nigerian English (one-time cost)

### 4. Payment Processing
- **Encourage bank transfers** over cards (₦50 vs ₦850 fee)
- **Negotiate volume discounts** with Paystack (possible at 10,000+ tx/month)
- **Add Flutterwave** as alternative (lower fees in some cases)
- **Pass fees to customers** optionally (transparency++)

### 5. Payroll Cost Reduction
- **Batch payouts weekly** instead of daily (fewer API calls)
- **Use Paystack Bulk Transfer API** (₦50 vs ₦100 for individual)
- **Implement retry logic** for failed transfers (avoid double fees)
- **Consider direct bank integration** for large enterprises

---

## 📈 Scaling Considerations

### At 1,000 Paying Customers
| Resource | Current | Required | Upgrade Cost |
|----------|---------|----------|--------------|
| **Database** | Mini (1M rows) | Standard (10M rows) | +₦6,500/month |
| **Dynos** | 1 web + 1 worker | 2 web + 2 worker | +₦22,750/month |
| **Redis** | Mini | Premium | +₦16,250/month |
| **S3** | 50GB | 500GB | +₦18,200/month |
| **Total Increase** | | | **+₦63,700/month** |

### At 10,000 Paying Customers
| Resource | Required | Cost | Notes |
|----------|----------|------|-------|
| **Heroku Performance Dynos** | 4 web + 4 worker | ₦520,000/month | $320/month |
| **PostgreSQL Standard** | 64M rows | ₦48,750/month | $30/month |
| **Redis Premium** | 5GB cache | ₦65,000/month | $40/month |
| **S3** | 5TB storage | ₦182,000/month | $112/month |
| **CDN** | CloudFlare Pro | ₦32,500/month | $20/month |
| **Total Infrastructure** | | **₦848,250/month** | |
| **Revenue** | 10,000 × ₦5,000 | **₦50,000,000/month** | |
| **Profit Margin** | | **~98.3%** | After variable costs |

---

## 🚨 Cost Alerts & Monitoring

### Set Up Alerts For:
1. **Heroku Dyno Usage** > 80% (scale up needed)
2. **Database Rows** > 8M (upgrade needed)
3. **S3 Storage** > 40GB (approaching limit)
4. **WhatsApp Messages** > 800/month (approaching free limit)
5. **OpenAI API Usage** > $50/month (unexpected voice volume)

### Monitoring Dashboard
```bash
# Monthly cost tracking
- Infrastructure: Fixed ₦78,325
- WhatsApp: Variable (free to ₦50,000)
- OpenAI: Variable (₦0 to ₦20,000)
- S3: Variable (₦1,000 to ₦10,000)
- Total: ₦79,325 to ₦158,325
```

---

## 💰 Final Cost Summary

### Per Invoice Cost (Text)
- **Minimum:** ₦3.06 (text only, excluding payment fee)
- **With Payment (₦50k):** ₦853.06 (including Paystack 1.5% + ₦100)

### Per Invoice Cost (Voice)
- **Minimum:** ₦8-13 (voice transcription included)
- **With Payment (₦50k):** ₦858-863

### Per Payroll Run (10 Workers)
- **Minimum:** ₦30.61 (excluding payouts)
- **With Payouts:** ₦530.61 (including ₦50/worker transfer fee)

### Monthly Infrastructure
- **Startup (Eco):** ₦45,825
- **Production (Basic):** ₦78,325
- **Scale (Performance):** ₦848,250 at 10,000 customers

### Break-Even Point
- **Invoice Business:** 37 Pro customers (₦5,000/month each)
- **Payroll Business:** 7 Enterprise customers (₦20,000/month each)

---

## 📊 Recommendations

### For Launch (0-100 customers)
1. Use Heroku Eco dynos (₦45,825/month)
2. Free Vercel Hobby plan
3. Minimize voice note usage (promote text)
4. Stay within WhatsApp free tier (1,000 messages)
5. **Total Monthly Cost:** ₦45,000 - ₦60,000

### For Growth (100-1,000 customers)
1. Upgrade to Heroku Basic (₦78,325/month)
2. Vercel Pro for better performance
3. Implement voice note length limits
4. Negotiate Paystack volume discount
5. **Total Monthly Cost:** ₦100,000 - ₦150,000

### For Scale (1,000+ customers)
1. Move to Performance dynos
2. Implement aggressive caching
3. Consider microservices architecture
4. Direct WhatsApp Business API contract
5. **Total Monthly Cost:** ₦500,000 - ₦1,000,000
6. **Expected Revenue:** ₦5,000,000 - ₦50,000,000

---

**Last Updated:** October 22, 2025  
**Next Review:** Monthly (track actual vs projected costs)
