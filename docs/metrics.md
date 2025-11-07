# Metrics & Observability

## Overview
This document outlines key authentication and invoicing metrics, recommended SLIs/SLOs, and PromQL examples for dashboards and alerting.

## Core Metrics
| Metric | Type | Description |
|--------|------|-------------|
| `invoice_created_total` | Counter | Invoices successfully created. |
| `invoice_paid_total` | Counter | Invoices marked paid. |
| `payment_confirmation_latency_seconds` | Histogram | Time from invoice creation to payment confirmation. |
| `otp_signup_requests_total` | Counter | OTP signup requests initiated. |
| `otp_signup_verifications_total` | Counter | Successful OTP signup verifications. |
| `otp_login_requests_total` | Counter | OTP login requests initiated. |
| `otp_login_verifications_total` | Counter | Successful OTP login verifications. |
| `otp_invalid_attempts_total` | Counter | Invalid/expired/blocked OTP attempts. |
| `otp_resends_total` | Counter | OTP resend attempts. |
| `otp_resends_blocked_total` | Counter | Resends blocked by cooldown. |
| `otp_signup_verify_latency_seconds` | Histogram | Latency (user completion) signup request → verification. Buckets tuned for 1–600s. |
| `otp_login_verify_latency_seconds` | Histogram | Latency (user completion) login request → verification. Buckets tuned for 1–600s. |
| `otp_whatsapp_delivery_success_total` | Counter | Successful WhatsApp OTP message deliveries. |
| `otp_whatsapp_delivery_failure_total` | Counter | Failed WhatsApp OTP message deliveries. |
| `otp_email_delivery_success_total` | Counter | Successful email OTP deliveries. |
| `otp_email_delivery_failure_total` | Counter | Failed email OTP deliveries. |
| `otp_resend_success_conversion_total` | Counter | Successful OTP verifications after at least one resend attempt. |

## SLIs & SLOs
| SLI | Definition | Suggested SLO |
|-----|------------|---------------|
| Signup success rate | `signup_verifications / signup_requests` | > 95% (monthly) |
| Login success rate | `login_verifications / login_requests` | > 97% (monthly) |
| OTP invalid attempt ratio | `invalid_attempts / (signup_requests + login_requests)` | < 30% (weekly) |
| Resend conversion rate | `resend_success_conversion / resends` | > 70% (monthly) |
| p95 signup latency | 95th percentile of `otp_signup_verify_latency_seconds` | < 60s (weekly) |
| p95 login latency | 95th percentile of `otp_login_verify_latency_seconds` | < 45s (weekly) |
| Invoice payment latency p95 | 95th percentile of `payment_confirmation_latency_seconds` | < 2h (monthly) |

## PromQL Examples
```
# Rates
sum(rate(otp_signup_verifications_total[5m])) / sum(rate(otp_signup_requests_total[5m]))
sum(rate(otp_login_verifications_total[5m])) / sum(rate(otp_login_requests_total[5m]))

# Invalid attempt ratio
sum(rate(otp_invalid_attempts_total[15m])) / sum(rate(otp_signup_requests_total[15m]) + rate(otp_login_requests_total[15m]))

# Percentiles
histogram_quantile(0.95, sum by (le) (rate(otp_signup_verify_latency_seconds_bucket[10m])))
histogram_quantile(0.95, sum by (le) (rate(otp_login_verify_latency_seconds_bucket[10m])))

# Invoice payment p95
histogram_quantile(0.95, sum by (le) (rate(payment_confirmation_latency_seconds_bucket[10m])))

# Delivery success rates
sum(rate(otp_whatsapp_delivery_success_total[5m])) / \
	(sum(rate(otp_whatsapp_delivery_success_total[5m])) + sum(rate(otp_whatsapp_delivery_failure_total[5m])))

sum(rate(otp_email_delivery_success_total[5m])) / \
	(sum(rate(otp_email_delivery_success_total[5m])) + sum(rate(otp_email_delivery_failure_total[5m])))

# Resend conversion rate
sum(rate(otp_resend_success_conversion_total[15m])) / sum(rate(otp_resends_total[15m]))
```

## Alerting Suggestions
| Condition | PromQL | Severity |
|-----------|--------|---------|
| Signup success < 90% for 15m | `sum(rate(otp_signup_verifications_total[15m])) / sum(rate(otp_signup_requests_total[15m])) < 0.9` | High |
| Invalid OTP attempts > 50% for 10m | `sum(rate(otp_invalid_attempts_total[10m])) / sum(rate(otp_signup_requests_total[10m]) + rate(otp_login_requests_total[10m])) > 0.5` | Medium |
| WhatsApp delivery failure rate > 5% for 15m | `sum(rate(otp_whatsapp_delivery_failure_total[15m])) / (sum(rate(otp_whatsapp_delivery_failure_total[15m])) + sum(rate(otp_whatsapp_delivery_success_total[15m]))) > 0.05` | Medium |
| Email delivery failure rate > 10% for 15m | `sum(rate(otp_email_delivery_failure_total[15m])) / (sum(rate(otp_email_delivery_failure_total[15m])) + sum(rate(otp_email_delivery_success_total[15m]))) > 0.10` | High (email less reliable early) |
| Resend conversion rate < 50% for 30m | `sum(rate(otp_resend_success_conversion_total[30m])) / sum(rate(otp_resends_total[30m])) < 0.5` | Low |
| p95 signup latency > 120s for 30m | `histogram_quantile(0.95, sum by (le) (rate(otp_signup_verify_latency_seconds_bucket[5m]))) > 120` | Medium |
| p95 login latency > 90s for 30m | `histogram_quantile(0.95, sum by (le) (rate(otp_login_verify_latency_seconds_bucket[5m]))) > 90` | Medium |

## Dashboard Panel Ideas
1. Success Funnel: Signup Requests → Signup Verifications (stacked rate graph).
2. Latency Percentiles: p50/p90/p95 for signup & login.
3. Invalid Attempt Ratio Over Time.
4. Resend Attempts vs Blocked Resends.
5. Invoice Creation vs Paid Conversion Rate.

## Notes
- OTP latency includes user action time; treat as *completion* not server latency.
- Avoid high-cardinality user labels; environment/job separation handled at scrape config.
- If needed later, add label `env` when counters are initialized (not required now).

## Future Enhancements
- Correlate resend usage to eventual verification (define a transient marker per identifier).
- Add gauge for active signup sessions (if needed for capacity planning).
- Add error counters for downstream delivery failures (SMTP, WhatsApp API).
