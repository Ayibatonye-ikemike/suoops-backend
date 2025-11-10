# Expense Tracking Feature - Implementation Plan

## Overview
WhatsApp and Email-based expense tracking to enable **accurate profit calculation** and **2026 Nigerian Tax Law compliance**.

## Problem Statement
Currently, SuoOps only tracks **revenue** (invoices), not expenses. This means:
- ❌ "Profit" shown is actually just revenue
- ❌ Users can't calculate actual taxable profit (Revenue - Expenses)
- ❌ Non-compliant with 2026 tax law requiring expense tracking
- ❌ Users overpay taxes because they can't deduct legitimate expenses

## Solution: Multi-Channel Expense Tracking

### Input Methods
1. **Voice/Audio** (WhatsApp/Email)
2. **Text Messages** (WhatsApp/Email)
3. **Photo Receipts** (OCR)
4. **Manual Entry** (Dashboard)

---

## Phase 1: Database Schema & Core Models

### 1.1 Expense Model
```python
class Expense(Base):
    """Business expense record"""
    __tablename__ = "expenses"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    
    # Amount & Date
    amount = Column(Numeric(15, 2), nullable=False)
    date = Column(Date, nullable=False, index=True)
    
    # Categorization
    category = Column(String(50), nullable=False, index=True)  # rent, data, supplies, etc.
    description = Column(String(500))
    merchant = Column(String(200))
    
    # Source tracking
    input_method = Column(String(20))  # voice, text, photo, manual
    channel = Column(String(20))  # whatsapp, email, dashboard
    
    # Receipt/Evidence
    receipt_url = Column(String(500))  # S3 URL for receipt image/PDF
    receipt_text = Column(Text)  # OCR extracted text
    
    # Verification
    verified = Column(Boolean, default=False)
    notes = Column(Text)
    
    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="expenses")
```

### 1.2 Expense Categories (Enum)
```python
class ExpenseCategory(str, Enum):
    """Nigerian business expense categories (tax-deductible)"""
    RENT = "rent"                       # Office/shop rent
    UTILITIES = "utilities"             # Electricity, water
    DATA_INTERNET = "data_internet"     # Internet, data bundles
    TRANSPORT = "transport"             # Fuel, transport fares
    SUPPLIES = "supplies"               # Office supplies, inventory
    EQUIPMENT = "equipment"             # Tools, machinery
    MARKETING = "marketing"             # Advertising, promotions
    PROFESSIONAL_FEES = "professional_fees"  # Accountant, lawyer
    STAFF_WAGES = "staff_wages"         # Employee salaries
    MAINTENANCE = "maintenance"         # Repairs
    OTHER = "other"                     # Miscellaneous
```

### 1.3 Migration
```python
"""Add expense tracking

Revision ID: add_expense_tracking
"""
def upgrade():
    op.create_table(
        'expenses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500)),
        sa.Column('merchant', sa.String(200)),
        sa.Column('input_method', sa.String(20)),
        sa.Column('channel', sa.String(20)),
        sa.Column('receipt_url', sa.String(500)),
        sa.Column('receipt_text', sa.Text()),
        sa.Column('verified', sa.Boolean(), default=False),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('ix_expenses_user_id', 'expenses', ['user_id'])
    op.create_index('ix_expenses_date', 'expenses', ['date'])
    op.create_index('ix_expenses_category', 'expenses', ['category'])
```

---

## Phase 2: Expense Input Processing

### 2.1 WhatsApp Voice/Text Handler
```python
class ExpenseIntentProcessor:
    """Extract expense from WhatsApp voice/text messages"""
    
    async def process_expense_message(
        self,
        user_id: int,
        message_text: str,
        audio_url: str | None = None
    ) -> Expense:
        """
        Parse expense from message:
        - "Expense: ₦2,000 for internet data on Nov 10"
        - "₦5,000 market rent November"
        """
        # 1. Transcribe audio if present
        if audio_url:
            message_text = await self.transcribe_audio(audio_url)
        
        # 2. Extract expense details using NLP
        expense_data = await self.nlp_service.extract_expense(message_text)
        
        # 3. Create expense record
        expense = Expense(
            user_id=user_id,
            amount=expense_data["amount"],
            date=expense_data["date"] or date.today(),
            category=expense_data["category"],
            description=expense_data["description"],
            merchant=expense_data.get("merchant"),
            input_method="voice" if audio_url else "text",
            channel="whatsapp",
        )
        
        self.db.add(expense)
        self.db.commit()
        
        # 4. Send confirmation
        await self.send_confirmation(user_id, expense)
        
        return expense
```

### 2.2 NLP Expense Extraction
```python
class ExpenseNLPService:
    """Extract expense details from natural language"""
    
    CATEGORY_KEYWORDS = {
        "rent": ["rent", "shop", "office", "space"],
        "data_internet": ["data", "internet", "airtime", "network"],
        "transport": ["transport", "fuel", "petrol", "taxi", "uber"],
        "supplies": ["supplies", "ink", "paper", "market", "stock"],
        "marketing": ["ads", "advertising", "promotion", "marketing"],
        # ... more categories
    }
    
    async def extract_expense(self, text: str) -> dict:
        """
        Extract: amount, category, date, description, merchant
        
        Examples:
        - "Expense ₦2,000 for data on Nov 10"
        - "₦5,000 market rent November"
        - "Paid ₦15,000 for shop rent today"
        """
        # 1. Extract amount
        amount = self._extract_amount(text)
        
        # 2. Extract date
        date_obj = self._extract_date(text)
        
        # 3. Categorize
        category = self._categorize(text)
        
        # 4. Extract merchant/description
        description = self._clean_description(text)
        merchant = self._extract_merchant(text)
        
        return {
            "amount": amount,
            "date": date_obj,
            "category": category,
            "description": description,
            "merchant": merchant,
        }
```

### 2.3 OCR Receipt Processing
```python
class ExpenseOCRService:
    """Extract expense from receipt photos"""
    
    async def process_receipt(
        self,
        user_id: int,
        image_url: str
    ) -> Expense:
        """
        Process receipt photo:
        1. OCR extraction
        2. Parse amount, date, merchant
        3. Categorize
        4. Create expense
        """
        # 1. Extract text from image
        ocr_result = await self.ocr_service.extract_text(image_url)
        
        # 2. Parse receipt data
        receipt_data = self._parse_receipt(ocr_result)
        
        # 3. Create expense
        expense = Expense(
            user_id=user_id,
            amount=receipt_data["amount"],
            date=receipt_data["date"],
            category=receipt_data.get("category", "other"),
            description=receipt_data.get("description"),
            merchant=receipt_data.get("merchant"),
            input_method="photo",
            channel="whatsapp",
            receipt_url=image_url,
            receipt_text=ocr_result,
        )
        
        self.db.add(expense)
        self.db.commit()
        
        return expense
```

---

## Phase 3: Expense API Endpoints

### 3.1 Create Expense (Manual Entry)
```python
@router.post("/expenses/", response_model=ExpenseOut)
def create_expense(
    data: ExpenseCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Create expense manually from dashboard"""
    expense = Expense(
        user_id=current_user_id,
        amount=data.amount,
        date=data.date,
        category=data.category,
        description=data.description,
        merchant=data.merchant,
        input_method="manual",
        channel="dashboard",
    )
    db.add(expense)
    db.commit()
    return expense
```

### 3.2 List Expenses
```python
@router.get("/expenses/", response_model=list[ExpenseOut])
def list_expenses(
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """List expenses with filters"""
    q = db.query(Expense).filter(Expense.user_id == current_user_id)
    
    if start_date:
        q = q.filter(Expense.date >= start_date)
    if end_date:
        q = q.filter(Expense.date <= end_date)
    if category:
        q = q.filter(Expense.category == category)
    
    return q.order_by(Expense.date.desc()).all()
```

### 3.3 Expense Summary
```python
@router.get("/expenses/summary")
def expense_summary(
    period_type: str = "month",  # day, week, month, year
    year: int | None = None,
    month: int | None = None,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Expense summary by category for period
    
    Returns:
    {
        "total_expenses": 28400,
        "by_category": {
            "rent": 15000,
            "data_internet": 3400,
            "supplies": 10000
        },
        "period_type": "month",
        "start_date": "2025-11-01",
        "end_date": "2025-11-30"
    }
    """
    # Calculate date range
    start_date, end_date = calculate_period_range(period_type, year, month)
    
    # Query expenses
    expenses = db.query(Expense).filter(
        Expense.user_id == current_user_id,
        Expense.date >= start_date,
        Expense.date <= end_date,
    ).all()
    
    # Aggregate by category
    by_category = {}
    total = Decimal("0")
    
    for expense in expenses:
        by_category[expense.category] = by_category.get(expense.category, Decimal("0")) + expense.amount
        total += expense.amount
    
    return {
        "total_expenses": float(total),
        "by_category": {k: float(v) for k, v in by_category.items()},
        "period_type": period_type,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
```

---

## Phase 4: Updated Tax Calculation

### 4.1 Profit Calculation (Revenue - Expenses)
```python
def compute_actual_profit(
    user_id: int,
    start_date: date,
    end_date: date,
    basis: str = "paid",
) -> Decimal:
    """
    Calculate ACTUAL profit: Revenue - Expenses
    
    This is the correct taxable profit per 2026 Nigerian Tax Law
    """
    # Revenue from invoices
    revenue = compute_revenue(user_id, start_date, end_date, basis)
    
    # Expenses
    expenses_total = db.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id,
        Expense.date >= start_date,
        Expense.date <= end_date,
    ).scalar() or Decimal("0")
    
    # Actual Profit
    profit = revenue - expenses_total
    
    return profit
```

### 4.2 Updated Tax Report Response
```python
{
    "revenue": 120000,              # Total income from invoices
    "expenses": 28400,              # Total business expenses
    "profit": 91600,                # Revenue - Expenses
    "taxable_income": 91600,        # Same as profit (before deductions)
    "pit_band": "0%",               # PIT rate for this income level
    "estimated_tax": 0,             # Tax amount
    "vat_collected": 9000,
    "levy_amount": 0,               # No levy for small businesses
    "warning": null,                # No warning if expenses tracked
}
```

---

## Phase 5: WhatsApp Bot Integration

### 5.1 Expense Command Handler
```python
# In app/bot/message_handler.py

async def handle_expense_message(self, message: dict):
    """Handle expense-related messages"""
    user_id = message["user_id"]
    text = message.get("text", "")
    image_url = message.get("image_url")
    audio_url = message.get("audio_url")
    
    # Check if it's an expense message
    if self._is_expense_message(text) or audio_url or image_url:
        # Process based on input type
        if image_url:
            expense = await self.expense_ocr.process_receipt(user_id, image_url)
        elif audio_url:
            expense = await self.expense_processor.process_expense_message(
                user_id, text, audio_url
            )
        else:
            expense = await self.expense_processor.process_expense_message(
                user_id, text
            )
        
        # Send confirmation
        confirmation = (
            f"✅ Added: ₦{expense.amount:,.0f} for {expense.description}\n"
            f"📅 Date: {expense.date.strftime('%b %d, %Y')}\n"
            f"📂 Category: {expense.category.replace('_', ' ').title()}"
        )
        
        await self.send_message(user_id, confirmation)
```

### 5.2 Expense Detection
```python
def _is_expense_message(self, text: str) -> bool:
    """Detect if message is about expense"""
    expense_triggers = [
        "expense",
        "spent",
        "paid for",
        "bought",
        "purchase",
        "₦",  # Naira symbol
    ]
    
    text_lower = text.lower()
    return any(trigger in text_lower for trigger in expense_triggers)
```

---

## Phase 6: Automated Reports & Reminders

### 6.1 Daily/Weekly/Monthly Summary
```python
@celery_app.task
def send_expense_summary(user_id: int, period: str = "weekly"):
    """Send expense summary via WhatsApp/Email"""
    
    # Calculate period
    if period == "daily":
        start_date = date.today()
        end_date = date.today()
    elif period == "weekly":
        start_date = date.today() - timedelta(days=7)
        end_date = date.today()
    elif period == "monthly":
        start_date = date.today().replace(day=1)
        end_date = date.today()
    
    # Get summary
    summary = get_expense_summary(user_id, start_date, end_date)
    revenue = get_revenue(user_id, start_date, end_date)
    profit = revenue - summary["total_expenses"]
    
    # Format message
    message = f"""
📊 {period.title()} Financial Summary

💰 Total Income: ₦{revenue:,.0f}
💸 Total Expenses: ₦{summary['total_expenses']:,.0f}
✅ Profit: ₦{profit:,.0f}

📂 Expenses by Category:
"""
    
    for category, amount in summary["by_category"].items():
        message += f"  • {category.replace('_', ' ').title()}: ₦{amount:,.0f}\n"
    
    # Send via WhatsApp
    whatsapp_client.send_message(user_id, message)
```

### 6.2 Reminder Tasks
```python
@celery_app.task
def send_expense_reminders():
    """Send reminders to record expenses"""
    
    # Get users who haven't recorded expenses this week
    one_week_ago = date.today() - timedelta(days=7)
    
    users = db.query(User).filter(
        ~User.expenses.any(Expense.date >= one_week_ago)
    ).all()
    
    for user in users:
        message = (
            "👋 Hi! Don't forget to send your weekly expenses to stay compliant "
            "and maximize your deductions!\n\n"
            "📸 Snap a photo of receipts\n"
            "🎤 Send a voice note\n"
            "✍️ Or type: 'Expense ₦1000 for data'"
        )
        
        whatsapp_client.send_message(user.id, message)
```

---

## Phase 7: Frontend Dashboard

### 7.1 Expense List Page
```tsx
// app/(dashboard)/dashboard/expenses/page.tsx

export default function ExpensesPage() {
  const [period, setPeriod] = useState<"day" | "week" | "month" | "year">("month");
  const { data: expenses } = useExpenses(period);
  const { data: summary } = useExpenseSummary(period);
  
  return (
    <div>
      <h1>Expenses</h1>
      
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          label="Total Expenses"
          value={`₦${summary?.total_expenses.toLocaleString()}`}
        />
        <StatCard
          label="Categories"
          value={Object.keys(summary?.by_category || {}).length}
        />
        <StatCard
          label="This Period"
          value={period}
        />
      </div>
      
      {/* Category Breakdown */}
      <CategoryChart data={summary?.by_category} />
      
      {/* Expense List */}
      <ExpenseTable expenses={expenses} />
    </div>
  );
}
```

---

## Implementation Timeline

### Week 1-2: Foundation
- [ ] Create Expense model & migration
- [ ] Build expense API endpoints
- [ ] Add manual expense entry in dashboard

### Week 3-4: WhatsApp Integration
- [ ] Implement expense NLP extraction
- [ ] Add WhatsApp expense message handler
- [ ] Voice transcription support

### Week 5-6: OCR & Advanced Features
- [ ] Implement OCR receipt processing
- [ ] Add expense categorization
- [ ] Build expense summary reports

### Week 7-8: Tax Integration
- [ ] Update profit calculation (Revenue - Expenses)
- [ ] Implement PIT progressive tax
- [ ] Update tax reports with actual profit

### Week 9-10: Automation & Polish
- [ ] Automated summaries (daily/weekly/monthly)
- [ ] Expense reminders
- [ ] Dashboard visualizations

---

## Success Metrics

1. **Adoption**: % of users recording expenses weekly
2. **Accuracy**: Profit calculations with expense deductions
3. **Compliance**: Tax-ready reports with expense breakdown
4. **Engagement**: WhatsApp expense messages per user
5. **Retention**: Users continuing to track expenses month-over-month

---

## Next Steps

1. Review & approve this plan
2. Create Phase 1 migration
3. Build core expense API
4. Integrate with WhatsApp bot
5. Deploy incrementally with feature flags
