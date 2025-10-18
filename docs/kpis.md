# KPIs & Success Metrics

Metrics are grouped by lifecycle stage. Instrument via a thin metrics module (e.g., Prometheus client) to keep services focused (SRP). Avoid embedding raw counter increments across code; expose functions like `metrics.invoice_created()`.

## Acquisition & Activation
| Metric | Definition | Target (Pilot) | Notes |
|--------|------------|----------------|-------|
| New Merchants / Week | Count of distinct users registering | 50 | Growth funnel top |
| First Invoice Time | Median minutes from registration → first invoice | < 5 min | Measures onboarding friction |
| Parse Success Rate | Successful parse / parse attempts (invoice intent) | ≥95% | Count fallback/unknown intents |

## Engagement
| Metric | Definition | Target | Notes |
|--------|------------|--------|-------|
| Weekly Active Merchants (WAM) | Users with ≥1 invoice or payroll action in a week | ≥60% of cumulative | Stickiness |
| Invoices per Active Merchant | Total invoices / WAM | 5 baseline → 8 | Expansion metric |
| Payroll Adoption Ratio | Merchants running ≥1 payroll / total merchants | 15% pilot | Cross-module adoption |

## Conversion & Financial
| Metric | Definition | Target | Notes |
|--------|------------|--------|-------|
| Payment Conversion | Paid invoices / total invoices (within due) | ≥70% | Excludes overdue beyond 7 days |
| Avg Payment Confirmation Latency | Mean seconds webhook-> status update | <10s | Per provider; monitor tail |
| Free → Paid Upgrade Rate | Paying merchants / merchants hitting free limit | 8–12% | After limit gating |
| Payment Margin Revenue | Sum(per-payment fees) | Track | Monetization baseline |

## Retention & Cohort
| Metric | Definition | Target | Notes |
|--------|------------|--------|-------|
| 4-Week Retention | Users active in Week 1 still active Week 4 | ≥40% | Monitor drop-offs |
| Churn Rate | (Inactive merchants prior 14d) / total merchants | <20% | Rolling window |

## Reliability & Performance
| Metric | Definition | Target | Notes |
|--------|------------|--------|-------|
| P95 Create Invoice Latency | API latency excluding network | <500ms | Warm path only |
| PDF Generation Success Rate | Successful / attempted PDF generations | ≥99.5% | Retry on transient failure |
| Webhook Idempotency Failures | Duplicate state transitions detected | 0 | Use hash store |
| WhatsApp Send Failure Rate | Failed messages / total sends after retries | <1% | Queue metrics |

## Data Quality & Parsing
| Metric | Definition | Target | Notes |
|--------|------------|--------|-------|
| NLP Unknown Intent Rate | Unknown intents / total messages | <5% | Segment by merchant maturity |
| OCR Total Extraction Accuracy | Correct total / total valid samples | ≥70% (prototype) | Later raise to 85% |

## Security & Compliance
| Metric | Definition | Target | Notes |
|--------|------------|--------|-------|
| Auth Failure Rate Spike | Rolling z-score of failed logins | Monitor | Brute force detection |
| Secrets Leak Incidents | Logged secrets occurrences | 0 | Static scan + runtime filter |

## Operational & Cost
| Metric | Definition | Target | Notes |
|--------|------------|--------|-------|
| Worker Queue Backlog Age | Oldest task age | <30s | For reminder jobs |
| DB CPU Utilization | Avg business hours | <60% | Scale threshold |
| Error Budget Consumption | SLO error minutes / month | <25% | Inclusive of 5xx & failed critical flows |

## Instrumentation Strategy
1. Wrapper module `metrics.py` exposing semantic functions so domain code calls `metrics.invoice_created()` (prevents metric name duplication – DRY).
2. Prometheus client counters/histograms names:
   - `invoice_created_total`
   - `invoice_paid_total`
   - `invoice_create_latency_seconds` (histogram)
   - `payment_confirmation_latency_seconds`
   - `whatsapp_parse_unknown_total`
   - `ocr_extraction_attempt_total`, `ocr_total_extracted_total`
3. Middleware adds `X-Request-ID` for correlation; include in logs for join with metrics.
4. Scheduled job publishes daily aggregates (persist snapshot to analytics table for longitudinal queries without expensive historical scans).

## Alert Threshold Examples
- Payment webhook latency P95 > 30s for 5 min → WARN.
- Invoice create error rate > 2% over 10 min → PAGE.
- Unknown intent rate > 10% daily → INVESTIGATE NLP regression.
- OCR accuracy sliding average < 50% → DISABLE feature flag.

## Metric Ownership
- Product Metrics (Activation/Engagement): Product Owner.
- Reliability & Performance: DevOps/SRE.
- NLP & OCR Quality: NLP/AI Engineer.
- Security & Compliance: Security/DevOps.

## Future Metrics (Phase 2+)
- Credit Score Eligibility (derived) – invoices paid velocity & average payment size.
- Worker Payout On-Time Rate – payroll run vs expected pay date.
- Loan Default Predictor Input Coverage – proportion of required financial signals present.
