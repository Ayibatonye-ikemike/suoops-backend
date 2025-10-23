# Team Roles & Resourcing Plan

Lean team design aligns to service boundaries—each role owns a vertical slice while preserving SRP at code level.

## Core Roles (MVP)
| Role | Primary Ownership | Key Modules / Services | Est. FTE | Notes |
|------|-------------------|------------------------|----------|-------|
| Backend Engineer (Invoices) | Invoice + Payment flows | `InvoiceService`, `PaymentService`, `PDFService` | 1.0 | Also supports migrations |
| Backend Engineer (Platform & Integrations) | Manual bank confirmations + Webhooks + Background jobs | `PaymentService`, `NotificationService`, `WhatsAppHandler`, `tasks`, metrics | 1.0 | Cross-trains on payments |
| Frontend / Dashboard Engineer | Minimal dashboard + auth UI + metrics view | (Future) React/PWA (not yet scaffolded) | 0.5–1.0 | Can be part-time until Week 5 |
| Product Manager / Analyst | Backlog trim, KPI monitoring, pilot feedback | `docs/` upkeep, metrics definitions | 0.5 | Ensures scope discipline |
| DevOps / SRE (Fractional) | CI/CD, infra, observability, security hardening | Docker, deployment scripts, metrics stack | 0.3–0.5 | Scales later |
| QA / Test Engineer (Fractional) | Automated test harness, performance smoke | Pytest suites, load scripts | 0.3 | Could be combined with backend early |
| NLP / OCR Engineer (Later) | Advanced parsing + OCR accuracy | `NLPService` enhancements, `OCRService` | 0.3 (Week 9+) | Optional until OCR milestone |

## Sequencing by Weeks
| Weeks | Critical Roles Active | Justification |
|-------|-----------------------|---------------|
| 1–2 | Backend (Invoices), DevOps light | Bootstrapping core services & migrations |
| 3–4 | + Backend (Platform), QA start | Payment & receipt flows, idempotency tests |
| 5–6 | + Frontend (Dashboard) | Need read-only UI & auth integration |
| 7–8 | + SRE focus increase | Overdue jobs, QR, rate limiting require observability |
| 9–10 | + NLP/OCR Engineer | Prototype OCR & enhanced parsing |
| 11–12 | All | Hardening, pre-pilot compliance & docs |

## Collaboration Model
- PR Review Matrix:
  - Payment changes require review by Backend (Invoices) + DevOps (security headers, secrets).
  - DB schema changes must include Alembic migration + forward/backward compatibility note.
  - NLP pattern changes gated behind regression test corpus update (`tests/nlp_cases.json`).
- Daily 15-min async standup (Slack thread) listing: Yesterday / Today / Blockers.
- Weekly risk review: highlight metrics drift (parse success or payment latency).

## Capacity Planning (Approx Story Points / Week)
| Role | Conservative Points/Week | Focus |
|------|--------------------------|-------|
| Backend (Invoices) | 20 | Domain logic + integrations |
| Backend (Platform) | 18 | Webhooks, bank confirmations, jobs |
| Frontend | 12 | UI, auth flows |
| QA | 10 | Test automation & perf scripts |

## Risk Mitigation via Role Coverage
- Single point of failure risk for payments -> cross-train Platform backend on PaymentService internals by Week 4.
- DevOps fractional load may bottleneck metrics: pre-create infra IaC templates Week 2.
- NLP expertise needed only after stable rule-base; delay hire until parse unknown rate >8% or OCR milestone kicks in.

## Skill Sets & Tooling
- Backend: Python (FastAPI, SQLAlchemy), async patterns, payment APIs, queue systems.
- DevOps: Containerization (Docker), CI (GitHub Actions), Observability (Prometheus/Grafana), Secrets management.
- Frontend: React + TypeScript (PWA offline-ready strategy), minimal design system.
- NLP/OCR: Regex/rule extraction, Tesseract, basic ML for entity extraction (future).

## Hiring Prioritization
1. Backend (Invoices) – critical path.
2. Platform Backend – parallelism & reduce bus factor.
3. Frontend – just-in-time before Week 5.
4. QA – early introduction reduces regression risk by M2.
5. NLP/OCR – optional until feature flagged.

## Documentation Ownership
- Each service folder must have a `README.md` overview (add in future sprint) kept under 100 LOC.
- Architecture diagram updates owned by Product Manager after each milestone.
- Runbooks: DevOps drafts; Backend validates domain-specific steps.

## Expansion Plan (Post-MVP)
- Introduce Finance/Compliance Advisor (part-time) for payout & credit scoring roadmap.
- Data Engineer when events volume > 50k/day (move to streaming ingestion).
