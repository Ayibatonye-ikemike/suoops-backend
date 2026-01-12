# WhatsApp Bot Templates Roadmap

> **Status:** Planned for future development  
> **Last Updated:** January 2026

This document outlines planned WhatsApp Business API templates to simulate dashboard functionality directly in WhatsApp conversations.

---

## 📊 Dashboard Summary Templates

### Invoice & Payment Templates

| Template Name | Purpose | Variables |
|---------------|---------|-----------|
| `invoice_summary` | Daily/weekly invoice overview | `{{pending_count}}`, `{{total_pending}}`, `{{paid_count}}`, `{{paid_total}}` |
| `payment_received_alert` | Real-time payment notification | `{{customer_name}}`, `{{amount}}`, `{{invoice_no}}` |
| `overdue_reminder` | Alert for overdue invoices | `{{count}}`, `{{invoice_no}}`, `{{days}}` |
| `weekly_revenue_report` | Weekly revenue summary | `{{revenue}}`, `{{invoice_count}}`, `{{percent}}` |
| `low_balance_alert` | Wallet balance warning | `{{balance}}` |
| `new_customer_notification` | New customer added | `{{name}}`, `{{email}}` |

### Interactive Dashboard Templates (with Buttons)

| Template Name | Message | Buttons |
|---------------|---------|---------|
| `invoice_status_check` | "Invoice #{{no}}: {{status}}" | `[Mark Paid]` `[Send Reminder]` `[View Details]` |
| `daily_digest` | "Today: {{new_invoices}} new, {{payments}} paid" | `[Create Invoice]` `[View Dashboard]` |
| `payment_confirmation` | "Confirm ₦{{amount}} from {{customer}}?" | `[Yes, Received]` `[Not Yet]` |
| `morning_digest` | "Good morning {{name}}! Yesterday: ₦{{collected}}. Today: {{due_count}} invoices due." | `[View Details]` `[Create Invoice]` |

---

## 📊 Tax Templates

### VAT & Tax Notification Templates

| Template Name | Purpose | Variables |
|---------------|---------|-----------|
| `vat_summary` | Monthly VAT summary | `{{month}}`, `{{output}}`, `{{input}}`, `{{net}}` |
| `vat_filing_reminder` | Filing deadline reminder | `{{days}}`, `{{due_date}}`, `{{amount}}` |
| `vat_filing_confirmation` | Filing success notification | `{{period}}`, `{{ref_no}}`, `{{amount}}` |
| `wht_summary` | WHT collected summary | `{{total}}`, `{{count}}` |
| `tax_calendar_alert` | Upcoming tax deadline | `{{tax_type}}`, `{{date}}`, `{{amount}}` |
| `annual_tax_summary` | Year-end tax overview | `{{vat}}`, `{{wht}}`, `{{cit}}` |

### Interactive Tax Templates

| Template Name | Message | Buttons |
|---------------|---------|---------|
| `quick_vat_check` | "Your VAT status for {{month}}?" | `[View Summary]` `[File Now]` |
| `filing_nudge` | "Ready to file {{period}} VAT?" | `[Yes, File]` `[Remind Later]` |

### Sample Message Formats

```
📊 *VAT Summary (December 2025)*
Output VAT: ₦125,000
Input VAT: ₦45,000
Net Payable: ₦80,000

⚠️ Filing due in 5 days (21st Jan)
```

```
✅ VAT return filed for Q4 2025
Reference: FIRS-2025-Q4-12345
Amount: ₦320,000
```

---

## 📦 Inventory Templates

### Stock Alert Templates

| Template Name | Purpose | Variables |
|---------------|---------|-----------|
| `low_stock_alert` | Low stock warning | `{{product_name}}`, `{{qty}}`, `{{reorder_level}}` |
| `stock_summary` | Inventory snapshot | `{{count}}`, `{{low_count}}`, `{{out_count}}` |
| `stock_movement` | Stock added notification | `{{product}}`, `{{qty}}`, `{{new_total}}` |
| `purchase_order_status` | PO status update | `{{po_no}}`, `{{supplier}}`, `{{status}}`, `{{date}}` |
| `daily_stock_report` | Daily movement summary | `{{sold_qty}}`, `{{sold_value}}`, `{{restock_qty}}` |
| `stock_valuation` | Total inventory value | `{{total_value}}`, `{{item_count}}` |

### Interactive Inventory Templates

| Template Name | Message | Buttons |
|---------------|---------|---------|
| `reorder_prompt` | "{{product}} is low ({{qty}} left). Reorder?" | `[Create PO]` `[Ignore]` |
| `stock_check` | "Check stock for {{product}}?" | `[View Stock]` `[Add Stock]` |
| `po_approval` | "Approve PO #{{no}} for ₦{{amount}}?" | `[Approve]` `[Reject]` |

### Sample Message Formats

```
⚠️ *Low Stock Alert*
Printer Paper A4: 5 packs left (min: 20)

Reply "reorder" to create purchase order
```

```
📦 *Inventory Snapshot*
Total Products: 156
Low Stock: 8 items
Out of Stock: 2 items

📥 Today's Movement:
Sold: 45 items (₦234,500)
Restocked: 120 items
```

---

## 🚀 Implementation Priority

### Phase 1 - High Value (Quick Wins)
1. **Payment received alert** - Real-time Paystack webhook trigger
2. **Morning digest** - Scheduled 8am daily summary
3. **Low stock alert** - Triggered when stock drops below threshold

### Phase 2 - Tax Compliance
1. **VAT filing reminder** - 5 days before due date
2. **Monthly VAT summary** - Auto-send on 1st of month
3. **Tax calendar alerts** - Scheduled based on Nigerian tax calendar

### Phase 3 - Inventory Management
1. **Stock summary on demand** - User requests via keyword
2. **Daily stock report** - Scheduled evening summary
3. **PO approval flow** - Interactive approval workflow

---

## ⚠️ Known Limitations

| Feature | Limitation | Workaround |
|---------|------------|------------|
| Full inventory list | Too long for WhatsApp (1024 char limit) | Show "Top 10 low stock" instead |
| Stock adjustments | Needs quantity input | Multi-step conversation flow |
| Product creation | Too many fields required | Link to dashboard |
| Tax filing workflow | Complex multi-step process | Link to dashboard with pre-filled data |
| Detailed VAT breakdown | Per-invoice breakdown too verbose | Summary only, link for details |
| Charts/graphs | Not supported natively | Send as image attachment |
| Bulk operations | WhatsApp is 1:1 conversation | Process one at a time or link to dashboard |

---

## 📋 Template Approval Notes

WhatsApp Business API requires Meta approval for message templates:

1. **Utility templates** (transactional) - Faster approval, higher delivery
2. **Marketing templates** - Slower approval, may require opt-in proof
3. **Authentication templates** - OTP/verification, fastest approval

**Recommended categories:**
- Payment alerts → Utility
- Tax reminders → Utility  
- Stock alerts → Utility
- Digests/reports → Marketing (unless transactional trigger)

---

## 🔗 Related Documentation

- [WhatsApp Business Setup](./whatsapp-business-guide.md)
- [WhatsApp Meta Configuration](./whatsapp-meta-setup.md)
- [Webhook Integration](./whatsapp-webhook-test.md)
