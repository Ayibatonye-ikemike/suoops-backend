# SuoOps Operational Cost Analysis 💰

**Last Updated:** January 22, 2026  
**Currency:** Nigerian Naira (₦) and USD ($)  
**Exchange Rate:** ₦1,625 = $1

---

## Executive Summary

### Total Monthly Operating Costs (Current)
| Category | Amount | Notes |
|----------|--------|-------|
| **Infrastructure** | ₦244,075 | Render, Vercel, Brevo, S3 |
| **WhatsApp Business API** | ~₦40,625 | 2,500 tier (~$25) |
| **Zoho Social** | ~₦16,250 | Social media management (~$10) |
| **Social Media Ads** | ₦80,000 | 4 accounts × ₦10k × 2/month |
| **Virtual Assistant** | ₦100,000 | Full-time VA |
| **Performance Marketers** | ₦120,000+ | 3 cities (variable) |
| **Referral Commissions** | Variable | ₦500 per Pro referral |
| **TOTAL FIXED COSTS** | **~₦600,950** | Before referral payouts |

### Cost Per Invoice (Text-Based)
| Component | Cost | Notes |
|-----------|------|-------|
| WhatsApp Message (Outbound) | ₦8 - ₦16 | WhatsApp Business API |
| Database Write | ₦0.001 | Negligible (included in hosting) |
| PDF Generation | ₦0.01 | CPU/memory overhead |
| S3 Storage (per invoice) | ₦0.05 | AWS S3 standard storage |
| **YOUR TOTAL COST** | **~₦8-16** | **This is your actual cost** |

**Note:** Paystack fees (1.5% + ₦100) are NOT your cost - they're deducted from the business's payment.

---

## 📊 Detailed Cost Breakdown

### 1. Infrastructure Costs (Monthly)

#### Render Backend (Production)
| Resource | Plan | Cost | Notes |
|----------|------|------|-------|
| **Web Service** | Starter | $7/month | 512MB RAM, always-on |
| **Web Service** | Standard | $25/month | 2GB RAM, auto-scaling |
| **Background Worker** | Starter | $7/month | For Celery/async tasks |
| **PostgreSQL** | Starter | $7/month | 1GB storage, 97 connections |
| **PostgreSQL** | Standard | $20/month | 20GB storage, 200 connections |
| **Redis** | Starter | $10/month | 25MB cache |
| **Total (Starter)** | | **$31/month** | **₦50,375** @ ₦1,625/$1 |
| **Total (Standard - Recommended)** | | **$62/month** | **₦100,750** @ ₦1,625/$1 |

#### Vercel Frontend (Production)
| Resource | Plan | Cost | Notes |
|----------|------|------|-------|
| **Hosting** | Hobby | $0/month | Free for personal projects |
| **Hosting** | Pro | $20/month | For production/commercial |
| **Bandwidth** | | $0 | 100GB free on Hobby |
| **Build Minutes** | | $0 | Unlimited on all plans |
| **Total** | | **$0-20/month** | **₦0-32,500** |

#### Brevo Email Service
| Resource | Plan | Cost | Notes |
|----------|------|------|-------|
| **Email + SMTP** | Business | $66/month | 5,000 emails/month included |
| **Transactional Emails** | Included | $0 | OTP, invoices, notifications |
| **Marketing Emails** | Included | $0 | Campaigns, newsletters |
| **Total** | | **$66/month** | **₦107,250** |

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
| **Domain** | suoops.com | $12/year | GoDaddy/Namecheap |
| **DNS** | Vercel | $0/month | Free with Vercel nameservers |
| **SSL Certificate** | Let's Encrypt | $0/month | Free via Render |
| **Total** | | **$1/month** | **₦1,625** |

**Total Infrastructure (Starter):** ₦161,200/month  
**Total Infrastructure (Standard):** ₦244,075/month

---

### 2. Communication & Marketing Costs (Monthly)

#### WhatsApp Business API (2,500 Tier)
| Metric | Rate | Notes |
|--------|------|-------|
| **Monthly Plan** | ~$25/month | 2,500 message tier |
| **Marketing Messages** | $0.0099-0.0315/msg | ₦16-51 per message |
| **Utility Messages** | $0.005-0.008/msg | ₦8-13 per message |
| **Authentication Messages** | $0.005/msg | ₦8 per OTP message |
| **Service Messages** | Free (24hr window) | User-initiated conversations |
| **Total Estimated** | | **~₦40,625/month** |

#### Zoho Social (Social Media Management)
| Resource | Plan | Cost | Notes |
|----------|------|------|-------|
| **Zoho Social** | Standard | ~$10/month | Manage 4 social accounts |
| **Features** | Included | | Scheduling, analytics, monitoring |
| **Total** | | **~₦16,250/month** |

#### Social Media Advertising
| Platform | Budget | Frequency | Monthly Cost |
|----------|--------|-----------|--------------|
| **Instagram** | ₦10,000 | Every 2 weeks | ₦20,000 |
| **Facebook** | ₦10,000 | Every 2 weeks | ₦20,000 |
| **Twitter/X** | ₦10,000 | Every 2 weeks | ₦20,000 |
| **TikTok** | ₦10,000 | Every 2 weeks | ₦20,000 |
| **Total** | | | **₦80,000/month** |

---

### 3. Team & Acquisition Costs (Monthly)

#### Virtual Assistant
| Role | Salary | Responsibilities |
|------|--------|------------------|
| **VA (Full-time)** | ₦100,000/month | Marketer coordination, sales verification, support |
| **Total** | | **₦100,000/month** |

#### Performance Marketers (3 Cities: Bayelsa, Lagos, Port Harcourt)
| Component | Amount | Condition |
|-----------|--------|-----------|
| **Weekly Stipend** | ₦10,000/marketer | Min 10 paid subscribers per 5-day cycle |
| **Monthly Stipend (per marketer)** | ₦40,000 | If targets consistently met |
| **Commission** | ₦500/subscriber | Uncapped - per verified Pro signup |
| **Estimated Total (3 marketers)** | | **₦120,000 - ₦200,000+/month** |

**Performance Marketer Economics:**
| Scenario | Stipend | Subscribers | Commission | Total Earnings |
|----------|---------|-------------|------------|----------------|
| **Minimum (10/week)** | ₦40,000 | 40/month | ₦20,000 | ₦60,000 |
| **Target (20/week)** | ₦40,000 | 80/month | ₦40,000 | ₦80,000 |
| **High Performer (30/week)** | ₦40,000 | 120/month | ₦60,000 | ₦100,000 |

**Your Cost per Marketer Acquisition:**
- Each marketer acquires: 40-120 Pro subscribers/month
- Your acquisition cost: ₦500/subscriber (commission)
- But you earn: ₦5,000/subscriber (Pro subscription)
- **Net gain: ₦4,500/subscriber after commission**

#### Referral Program (User Commissions)
| Component | Amount | Notes |
|-----------|--------|-------|
| **Referral Commission** | ₦500/Pro subscriber | 10% of ₦5,000 Pro plan |
| **Payment Frequency** | Monthly | End of each month |
| **Estimated Monthly Payout** | Variable | Depends on referral volume |

**Referral Program Cost Projections:**
| Active Referrers | Avg Referrals/Month | Monthly Commission Payout |
|------------------|---------------------|---------------------------|
| 50 users | 2 each = 100 subs | ₦50,000 |
| 100 users | 2 each = 200 subs | ₦100,000 |
| 200 users | 2 each = 400 subs | ₦200,000 |

**Referral ROI:**
- You pay: ₦500 commission
- You earn: ₦5,000 subscription
- **Net gain: ₦4,500/subscriber (90% margin)**

---

### 4. Per-Transaction Costs

#### Paystack Payment Processing
| Transaction Type | Fee Structure | Example (₦50,000) |
|------------------|---------------|-------------------|
| **Local Card** | 1.5% + ₦100 | ₦850 |
| **Bank Transfer** | ₦50 flat | ₦50 |
| **USSD** | 1% capped at ₦2,000 | ₦500 |
| **International Card** | 3.9% + ₦100 | ₦2,050 |

**Important:** These fees are **NOT your operational cost**. They are:
- Deducted by Paystack from the payment
- Paid by the business (your customer)
- You never see or pay these fees

---

### 5. Cost Per Use Case

#### Scenario 1: Early Stage (50 Pro Customers)
| Cost Item | Amount | Notes |
|-----------|--------|-------|
| Infrastructure | ₦244,075 | Render Standard + Vercel Pro + Brevo |
| WhatsApp API | ₦40,625 | 2,500 tier |
| Zoho Social | ₦16,250 | Social media management |
| Social Media Ads | ₦80,000 | 4 platforms × ₦20k |
| Virtual Assistant | ₦100,000 | Team coordination |
| Performance Marketers | ₦120,000 | 3 marketers (stipend only) |
| Referral Commissions | ₦25,000 | ~50 referral signups |
| **Total Monthly** | **₦625,950** | **Fixed operational cost** |
| **Revenue (50 Pro)** | **₦250,000** | 50 × ₦5,000 |
| **Net Position** | **-₦375,950** | Growth investment phase |

#### Scenario 2: Growth Stage (200 Pro Customers)
| Cost Item | Amount | Notes |
|-----------|--------|-------|
| Infrastructure | ₦244,075 | Same |
| WhatsApp API | ₦40,625 | Same |
| Zoho Social | ₦16,250 | Same |
| Social Media Ads | ₦80,000 | Same |
| Virtual Assistant | ₦100,000 | Same |
| Performance Marketers | ₦180,000 | Higher commissions |
| Referral Commissions | ₦100,000 | ~200 referral signups |
| **Total Monthly** | **₦760,950** | |
| **Revenue (200 Pro)** | **₦1,000,000** | 200 × ₦5,000 |
| **Net Profit** | **₦239,050** | **23.9% margin** ✅

#### Scenario 3: Scale Stage (500 Pro Customers)
| Cost Item | Amount | Notes |
|-----------|--------|-------|
| Infrastructure | ₦300,000 | Scaled up |
| WhatsApp API | ₦60,000 | Higher tier |
| Zoho Social | ₦16,250 | Same |
| Social Media Ads | ₦120,000 | Increased budget |
| Virtual Assistant | ₦150,000 | Additional support |
| Performance Marketers | ₦300,000 | More marketers, higher volume |
| Referral Commissions | ₦250,000 | ~500 referral signups |
| **Total Monthly** | **₦1,196,250** | |
| **Revenue (500 Pro)** | **₦2,500,000** | 500 × ₦5,000 |
| **Net Profit** | **₦1,303,750** | **52.2% margin** ✅

## 💡 Profitability Analysis

### Subscription Pricing (Current)

| Plan | Price | Max Usage | Margin Analysis |
|------|-------|-----------|-----------------|
| **Free** | ₦0/month | 10 invoices | Loss leader for acquisition |
| **Pro** | ₦5,000/month | Unlimited invoices | Profitable at 200+ customers |

### Updated Break-Even Analysis (With Full Team Costs)

#### Current Monthly Burn Rate
| Category | Amount |
|----------|--------|
| Infrastructure | ₦244,075 |
| WhatsApp API (2,500 tier) | ₦40,625 |
| Zoho Social | ₦16,250 |
| Social Media Ads | ₦80,000 |
| Virtual Assistant | ₦100,000 |
| Performance Marketers (base) | ₦120,000 |
| **Total Fixed Costs** | **₦600,950** |

#### Variable Costs (Per Customer Acquired)
| Channel | Cost Per Acquisition | Notes |
|---------|---------------------|-------|
| Performance Marketer | ₦500 | Commission per Pro signup |
| Referral Program | ₦500 | 10% of ₦5,000 Pro plan |
| Organic (Ads/Social) | ~₦200-500 | Estimated CAC via ads |

#### Break-Even Calculation
**With all operational costs:**
- Fixed costs: ₦600,950/month
- Revenue per Pro customer: ₦5,000/month
- Break-even: ₦600,950 ÷ ₦5,000 = **121 Pro customers**

**But considering acquisition costs:**
- If 50% via marketers (₦500 commission): Net revenue = ₦4,500
- If 30% via referrals (₦500 commission): Net revenue = ₦4,500
- If 20% organic: Net revenue = ₦5,000
- Blended net revenue: ~₦4,600/customer
- **True break-even: ₦600,950 ÷ ₦4,600 = ~131 Pro customers**

### Revenue Projections (Updated)

#### Current Phase (0-100 Pro Customers)
| Metric | Amount |
|--------|--------|
| Monthly Revenue | ₦0 - ₦500,000 |
| Monthly Costs | ₦600,950 |
| Monthly Loss | ₦100,950 - ₦600,950 |
| Status | **Investment/Growth Phase** 📈 |

#### Growth Phase (100-200 Pro Customers)
| Metric | Amount |
|--------|--------|
| Monthly Revenue | ₦500,000 - ₦1,000,000 |
| Monthly Costs | ₦650,000 - ₦760,000 |
| Monthly Profit/Loss | -₦150,000 to +₦240,000 |
| Status | **Approaching Break-Even** ⚖️ |

#### Scale Phase (200+ Pro Customers)
| Metric | Amount |
|--------|--------|
| Monthly Revenue | ₦1,000,000+ |
| Monthly Costs | ₦760,000 - ₦1,200,000 |
| Monthly Profit | ₦240,000+ |
| Profit Margin | 20-50% |
| Status | **Profitable** ✅ |

---

## 👥 Customer Acquisition Cost (CAC) Analysis

### By Channel
| Channel | Cost/Acquisition | LTV (12 months) | LTV:CAC Ratio |
|---------|-----------------|-----------------|---------------|
| **Performance Marketers** | ₦500 | ₦60,000 | 120:1 ✅ |
| **Referral Program** | ₦500 | ₦60,000 | 120:1 ✅ |
| **Social Media Ads** | ~₦400-800 | ₦60,000 | 75-150:1 ✅ |
| **Organic** | ₦0 | ₦60,000 | ∞ ✅ |

### Marketer ROI
Each Performance Marketer acquiring 40 Pro customers/month:
- You pay: ₦40,000 stipend + ₦20,000 commission = ₦60,000
- You earn: 40 × ₦5,000 = ₦200,000/month
- **Net gain: ₦140,000/marketer/month**
- **ROI: 233%** ✅

### Referral Program ROI
Each referred Pro customer:
- You pay: ₦500 commission
- You earn: ₦5,000/month recurring
- **Payback: 1st month** ✅
- **12-month LTV: ₦60,000 - ₦500 = ₦59,500 profit**

---

## 🎯 Cost Optimization Strategies

### 1. Infrastructure Optimization
- **Use Render Starter** until you hit 100 users (saves ₦81,875/month)
- **Compress PDFs** before S3 upload (save 30-50% storage)
- **Cache frequently accessed invoices** in Redis (reduce S3 GET costs)
- **Use CloudFlare CDN** for static assets (free tier)

### 2. WhatsApp Cost Reduction
- **Batch notifications** instead of sending immediately
- **Use utility messages** over marketing (cheaper rates)
- **Leverage 24hr service window** for free conversations
- **Implement retry logic** to avoid duplicate sends

### 3. Email Optimization (Brevo)
- **Stay within 5,000 emails/month** to avoid overage
- **Use transactional for critical emails** (higher deliverability)
- **Batch marketing campaigns** efficiently

### 4. Payment Processing
- **Encourage bank transfers** over cards (₦50 vs ₦850 fee)
- **Negotiate volume discounts** with Paystack (possible at 10,000+ tx/month)
- **Pass fees to customers** optionally (transparency++)

## 📈 Scaling Considerations

### At 1,000 Paying Customers
| Resource | Current | Required | Upgrade Cost |
|----------|---------|----------|--------------|
| **Database** | Starter (1GB) | Pro (50GB) | +₦48,750/month |
| **Web Service** | Standard | Pro | +₦81,250/month |
| **Redis** | Starter | Pro | +₦48,750/month |
| **S3** | 50GB | 500GB | +₦18,200/month |
| **Total Increase** | | | **+₦196,950/month** |

### At 10,000 Paying Customers
| Resource | Required | Cost | Notes |
|----------|----------|------|-------|
| **Render Pro Web** | 2 instances | ₦325,000/month | $200/month |
| **Render Pro Worker** | 2 instances | ₦162,500/month | $100/month |
| **PostgreSQL Pro** | 100GB storage | ₦162,500/month | $100/month |
| **Redis Pro** | 1GB cache | ₦81,250/month | $50/month |
| **S3** | 5TB storage | ₦182,000/month | $112/month |
| **CDN** | CloudFlare Pro | ₦32,500/month | $20/month |
| **Brevo** | Business | ₦107,250/month | $66/month |
| **Total Infrastructure** | | **₦1,053,000/month** | |
| **Revenue** | 10,000 × ₦5,000 | **₦50,000,000/month** | |
| **Profit Margin** | | **~97.9%** | After variable costs |

---

## 🚨 Cost Alerts & Monitoring

### Set Up Alerts For:
1. **Render CPU/Memory Usage** > 80% (scale up needed)
2. **Database Storage** > 80% capacity (upgrade needed)
3. **S3 Storage** > 40GB (approaching limit)
4. **WhatsApp Messages** > 2,000/month (approaching 2,500 tier limit)
5. **Brevo Emails** > 4,000/month (approaching 5,000 limit)
6. **Performance Marketer payouts** > ₦200,000/month (review targets)

### Monitoring Dashboard
```bash
# Monthly cost tracking (Current)
- Infrastructure:        ₦244,075
- WhatsApp API:          ₦40,625
- Zoho Social:           ₦16,250
- Social Media Ads:      ₦80,000
- Virtual Assistant:     ₦100,000
- Performance Marketers: ₦120,000+
- Referral Commissions:  Variable
- Total Fixed:           ₦600,950
```

---

## 💰 Final Cost Summary

### Total Monthly Operating Costs
| Category | Amount | % of Total |
|----------|--------|------------|
| **Infrastructure** | ₦244,075 | 40.6% |
| **WhatsApp API** | ₦40,625 | 6.8% |
| **Zoho Social** | ₦16,250 | 2.7% |
| **Social Media Ads** | ₦80,000 | 13.3% |
| **Virtual Assistant** | ₦100,000 | 16.6% |
| **Performance Marketers** | ₦120,000 | 20.0% |
| **TOTAL FIXED** | **₦600,950** | 100% |

### Variable Costs (Scale with Growth)
| Cost Type | Amount | Trigger |
|-----------|--------|---------|
| **Marketer Commissions** | ₦500/subscriber | Each Pro signup via marketer |
| **Referral Commissions** | ₦500/subscriber | Each Pro signup via referral |
| **WhatsApp Overage** | ₦8-16/message | Beyond 2,500 tier |

### Break-Even Point (Updated)
- **With full team costs:** ~131 Pro customers
- **Revenue needed:** ₦655,000/month
- **Current burn rate:** ₦600,950/month

### Unit Economics
| Metric | Value |
|--------|-------|
| **Revenue per Pro** | ₦5,000/month |
| **Acquisition Cost (Marketer)** | ₦500 |
| **Acquisition Cost (Referral)** | ₦500 |
| **Net Revenue (after commission)** | ₦4,500-5,000 |
| **LTV (12 months)** | ₦60,000 |
| **LTV:CAC Ratio** | 120:1 ✅ |

### Key Insights 🎯

1. **Break-even requires ~131 Pro customers** with current team structure
2. **Marketers are highly ROI-positive** - Each marketer brings ₦140,000+ net/month
3. **Referral program is essentially free acquisition** - ₦500 commission vs ₦60,000 LTV
4. **Paystack fees are NOT your cost** - Deducted from customer payments
5. **Largest cost drivers:**
   - Infrastructure (40.6%)
   - Performance Marketers (20%)
   - Virtual Assistant (16.6%)
   - Social Media Ads (13.3%)

---

## 📊 Recommendations

### Current Phase (0-131 customers) - INVESTMENT
1. Focus on marketer-driven acquisition (best ROI)
2. Push referral program adoption (zero CAC after commission)
3. Optimize ad spend for conversion, not impressions
4. **Total Monthly Cost:** ₦600,950
5. **Target:** Hit 131 Pro customers ASAP for break-even

### Growth Phase (131-300 customers) - PROFITABILITY
1. Scale Performance Marketer program to more cities
2. Increase referral program incentives if needed
3. Consider reducing ad spend if organic is working
4. **Total Monthly Cost:** ₦700,000 - ₦900,000
5. **Expected Revenue:** ₦655,000 - ₦1,500,000

### Scale Phase (300+ customers) - EXPANSION
1. Hire additional VAs for support
2. Expand to more Nigerian cities
3. Consider enterprise tier (₦20,000+/month)
4. **Total Monthly Cost:** ₦1,000,000 - ₦1,500,000
5. **Expected Revenue:** ₦1,500,000 - ₦5,000,000+

---

## 📋 Cost Summary Table (Quick Reference)

| Cost Item | Monthly Amount | Annual Amount |
|-----------|----------------|---------------|
| Render (Standard) | ₦100,750 | ₦1,209,000 |
| Vercel Pro | ₦32,500 | ₦390,000 |
| Brevo Email ($66) | ₦107,250 | ₦1,287,000 |
| AWS S3 | ₦1,950 | ₦23,400 |
| Domain/DNS | ₦1,625 | ₦19,500 |
| WhatsApp API (2,500) | ₦40,625 | ₦487,500 |
| Zoho Social | ₦16,250 | ₦195,000 |
| Social Media Ads | ₦80,000 | ₦960,000 |
| Virtual Assistant | ₦100,000 | ₦1,200,000 |
| Performance Marketers | ₦120,000+ | ₦1,440,000+ |
| **TOTAL FIXED** | **₦600,950** | **₦7,211,400** |
| Referral Commissions | Variable | Variable |
| Marketer Commissions | Variable | Variable |

---

**Last Updated:** January 22, 2026  
**Next Review:** Monthly (track actual vs projected costs)
