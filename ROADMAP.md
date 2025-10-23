# WhatsInvoice - Development Roadmap

## ✅ Completed Features

### Authentication & User Management
- [x] User registration with phone/name/password
- [x] Login with JWT access tokens + HTTP-only refresh cookies
- [x] Session management with automatic refresh
- [x] Protected routes and auth middleware
- [x] Logout functionality

### Invoice Management
- [x] Create invoices with customer info and line items
- [x] List all invoices with status indicators
- [x] View invoice details
- [x] Update invoice status (pending → paid → failed)
- [x] Real-time invoice updates
- [x] PDF generation (basic with ReportLab)
- [x] Invoice webhook event tracking

### Banking & Manual Confirmation
- [x] Bank profile storage (business name, account details)
- [x] Manual payment confirmation flow for bank transfers
- [x] Awaiting confirmation status handling
- [x] Dashboard settings surfaces bank and plan information

### Infrastructure
- [x] FastAPI backend with SQLAlchemy ORM
- [x] PostgreSQL database with migrations
- [x] Redis for caching/tasks
- [x] Next.js 15 frontend with TypeScript
- [x] Tailwind CSS v4 for styling
- [x] React Query for data fetching
- [x] Zustand for state management
- [x] Comprehensive test suite (pytest)

---

## 🚀 Next Steps - Prioritized

### Phase 1: Core Functionality Completion (1-2 weeks)

#### 1.1 Testing & Bug Fixes
**Priority: CRITICAL**
- [ ] Test full invoice creation flow in browser
- [ ] Test invoice status updates
-- [ ] Test bank details update and manual confirmation flow
- [ ] Fix any UI/UX issues discovered
- [ ] Test registration and login flows thoroughly
- [ ] Test session expiry and refresh

#### 1.2 PDF Enhancement
**Priority: HIGH**
- [ ] Enable WeasyPrint for HTML-to-PDF conversion
- [ ] Design professional invoice PDF template
- [ ] Add company logo support
- [ ] Include payment QR code on invoice
- [ ] Implement S3/storage upload for PDFs
- [ ] Create `/invoices/{id}/download` endpoint to serve PDFs
- [ ] Remove file:// path issues

**Files to modify:**
- `app/services/pdf_service.py` - Enable WeasyPrint
- `templates/invoice.html` - Improve styling
- `app/api/routes_invoices.py` - Add download endpoint

#### 1.3 Invoice Details Page
**Priority: HIGH**
- [ ] Create `/dashboard/invoices/{id}` route
- [ ] Show full invoice details with customer info
- [ ] Display all line items in table
- [ ] Show payment link (if unpaid)
- [ ] Add status update UI
- [ ] Show audit trail/timeline of changes
- [ ] Add "Download PDF" button

**New files:**
- `frontend/app/(dashboard)/dashboard/invoices/[id]/page.tsx`
- `frontend/src/features/invoices/invoice-detail-page.tsx`

---

### Phase 2: WhatsApp Integration (2-3 weeks)

#### 2.1 WhatsApp Setup
**Priority: HIGH**
- [ ] Register with Meta for WhatsApp Business API
- [ ] Set up webhook endpoint
- [ ] Configure verification token
- [ ] Test connection with Meta's test numbers

#### 2.2 Message Handling
**Priority: HIGH**
- [ ] Implement webhook receiver at `/webhooks/whatsapp`
- [ ] Parse incoming text messages
- [ ] Implement NLP/intent detection for invoice commands
- [ ] Extract customer name, amount, items from message
- [ ] Send confirmation messages

**Example commands to parse:**
- "Create invoice for John Doe, ₦5000 for website design"
- "Invoice customer Mary, ₦3500 for 2x logo design"

#### 2.3 Outbound Messages
**Priority: HIGH**
- [ ] Send invoice details via WhatsApp
- [ ] Send PDF as attachment
- [ ] Send payment link
- [ ] Send payment confirmation
- [ ] Handle template messages for notifications

**Files to modify:**
- `app/bot/whatsapp_adapter.py` - Implement actual API calls
- `app/bot/nlp.py` - Improve intent parsing
- `app/services/notify_service.py` - Add WhatsApp notifications

---

### Phase 3: Payment Integration (2-3 weeks)

#### 3.1 Payment Provider Setup
**Priority: HIGH**
- [ ] Finalize Paystack provider configuration
- [ ] Register account and get API keys
- [ ] Configure webhook URL
- [ ] Test in sandbox mode

#### 3.2 Payment Flow
**Priority: HIGH**
- [ ] Generate payment links via provider API
- [ ] Store payment reference on invoice
- [ ] Implement webhook handler for payment events
- [ ] Update invoice status on successful payment
- [ ] Handle failed payments
- [ ] Send payment confirmation

**Files to modify:**
- `app/services/payment_service.py` - Implement actual provider calls
- `app/api/routes_webhooks.py` - Add payment webhook handler
- `app/services/invoice_service.py` - Link payment flow

#### 3.3 Payment History
**Priority: MEDIUM**
- [ ] Track all payment attempts
- [ ] Show payment history in invoice details
- [ ] Add payment method info
- [ ] Show transaction IDs

---

### Phase 4: Enhanced Features (3-4 weeks)

#### 4.1 Payment Confirmation History
**Priority: MEDIUM**
- [ ] Create `/dashboard/payments/history` page
- [ ] List all manual confirmations and webhook events
- [ ] Show details per confirmation (invoice, actor, timestamp)
- [ ] Calculate totals and summaries
- [ ] Add filtering by date range
- [ ] Export to CSV/Excel

#### 4.2 User Profile & Settings
**Priority: MEDIUM**
- [ ] Create `/dashboard/settings` page
- [ ] Edit profile (name, phone, email)
- [ ] Change password
- [ ] Business settings (company name, logo, tax info)
- [ ] WhatsApp settings (phone number, templates)
- [ ] Payment preferences
- [ ] Notification preferences

#### 4.3 Analytics Dashboard
**Priority: MEDIUM**
- [ ] Revenue trends chart (last 30/90 days)
- [ ] Invoice statistics (pending/paid/failed counts)
- [ ] Manual confirmation vs webhook success rate
- [ ] Top customers by revenue
- [ ] Payment timing distribution (avg days to pay)
- [ ] Monthly/yearly summaries

**New files:**
- `frontend/app/(dashboard)/dashboard/analytics/page.tsx`
- `frontend/src/features/analytics/` - Chart components

#### 4.4 Email Notifications
**Priority: MEDIUM**
- [ ] Set up email service (SendGrid/AWS SES)
- [ ] Send invoice created notification
- [ ] Send payment received notification
- [ ] Add email preferences in settings
- [ ] Email templates with branding

---

### Phase 5: Advanced Features (4+ weeks)

#### 5.1 Multi-Currency Support
- [ ] Add currency field to invoices
- [ ] Support USD, GBP, EUR alongside NGN
- [ ] Currency conversion rates
- [ ] Display amounts in user's preferred currency

#### 5.2 Recurring Invoices
- [ ] Set up recurring invoice schedules
- [ ] Automatic invoice generation
- [ ] Send reminders before due date
- [ ] Track subscription-like customers

#### 5.3 Customer Management
- [ ] Create `/dashboard/customers` page
- [ ] Add/edit customer details
- [ ] View customer invoice history
- [ ] Track customer lifetime value
- [ ] Add notes/tags to customers

#### 5.4 Expense Tracking
- [ ] Record business expenses
- [ ] Categorize expenses
- [ ] Link expenses to invoices/projects
- [ ] Generate expense reports
- [ ] Calculate profit margins

#### 5.5 Mobile App
- [ ] React Native mobile app
- [ ] Push notifications
- [ ] Offline mode
- [ ] Camera for receipt scanning (OCR)

---

## 🔧 Technical Improvements

### Infrastructure
- [ ] Set up CI/CD pipeline (GitHub Actions)
- [ ] Configure production environment
- [ ] Set up monitoring (Sentry, DataDog)
- [ ] Add rate limiting to API
- [ ] Implement API versioning
- [ ] Add caching strategies
- [ ] Database optimization (indexes, queries)
- [ ] Add database backups

### Security
- [ ] Implement 2FA for login
- [ ] Add CORS configuration
- [ ] Set up CSP headers
- [ ] Implement rate limiting per user
- [ ] Add audit logging for sensitive actions
- [ ] Encrypt sensitive data at rest
- [ ] Security audit and penetration testing

### Testing
- [ ] Increase test coverage to >80%
- [ ] Add E2E tests with Playwright
- [ ] Add frontend unit tests (Vitest)
- [ ] Add load testing (Locust)
- [ ] Add integration tests for WhatsApp
- [ ] Add integration tests for payments

### Documentation
- [ ] API documentation (auto-generated from OpenAPI)
- [ ] User guide/help center
- [ ] Video tutorials
- [ ] Developer onboarding docs
- [ ] Deployment guide
- [ ] Architecture diagrams

---

## 📊 Metrics to Track

### Business Metrics
- Total invoices created
- Total revenue processed
- Average invoice value
- Payment success rate
- Customer retention rate
- Manual confirmation volume

### Technical Metrics
- API response times
- Error rates
- Uptime/availability
- Database query performance
- PDF generation time
- WhatsApp message delivery rate

---

## 🎯 Suggested Focus for Next Sprint

**Week 1-2: Core Completion**
1. Complete browser testing
2. Implement PDF download endpoint
3. Create invoice detail page
4. Fix any critical bugs

**Week 3-4: WhatsApp MVP**
1. Set up WhatsApp Business API
2. Implement basic webhook
3. Parse simple invoice commands
4. Send invoice via WhatsApp

**Week 5-6: Payment Integration**
1. Choose and set up payment provider
2. Generate payment links
3. Handle payment webhooks
4. Update invoice status on payment

This roadmap will take your MVP to a production-ready state in ~12-16 weeks of focused development!

