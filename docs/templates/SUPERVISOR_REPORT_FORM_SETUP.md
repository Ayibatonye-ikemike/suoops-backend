# 📝 Supervisor Daily Report Form - Setup Guide

## New Workflow

```
Marketers → Report to Supervisor (WhatsApp)
                    ↓
Supervisor → Submits ONE form with ALL team data
                    ↓
Google Sheet → Auto-calculates everything
```

**Only Supervisors and Sr. Supervisors fill the form!**

---

## How It Works

| Role | What They Do |
|------|--------------|
| **Marketer** | Reports daily to Supervisor via WhatsApp/call |
| **Supervisor** | Collects team data, submits ONE Google Form daily |
| **Sr. Supervisor** | Submits their own sales + can view all teams |
| **VA** | Sends reminders, verifies weekly with app dashboard |

---

## Step 1: Create the Supervisor Report Form

### Go to [forms.google.com](https://forms.google.com) → Click **+ Blank**

### Form Title:
```
📊 SuoOps Supervisor Daily Team Report
```

### Form Description:
```
Supervisors: Submit your team's daily sales by 9 PM.
Collect data from your marketers first, then fill this form.
```

---

## Step 2: Form Questions

### Section 1: Your Info

#### Q1: Your Supervisor/Sr. Supervisor ID
- **Type:** Short answer
- **Required:** Yes
- **Help text:** `Example: SUO-SUP-001 or SUO-SSR-001`

#### Q2: Date
- **Type:** Date
- **Required:** Yes

#### Q3: Your Personal Pro Sales Today
- **Type:** Number
- **Required:** Yes
- **Help text:** `Your own sales (not team)`

---

### Section 2: Team Member 1

#### Q4: Marketer 1 ID
- **Type:** Short answer
- **Required:** No
- **Help text:** `Example: SUO-MKT-001 (leave blank if no team member)`

#### Q5: Marketer 1 Pro Sales Today
- **Type:** Number
- **Required:** No

---

### Section 3: Team Member 2

#### Q6: Marketer 2 ID
- **Type:** Short answer
- **Required:** No

#### Q7: Marketer 2 Pro Sales Today
- **Type:** Number
- **Required:** No

---

### (Repeat for Team Members 3-10)

*Add sections for up to 10 team members*

---

### Final Section: Summary

#### Q24: Total Team Sales Today
- **Type:** Number
- **Required:** Yes
- **Help text:** `Sum of all team members + your own sales`

#### Q25: Notes
- **Type:** Paragraph
- **Required:** No
- **Help text:** `Any issues? Who was absent? Top performers?`

---

## Step 3: Alternative - Simpler Grid Format

Instead of individual questions, use a **Grid**:

### Q4: Team Sales Today (Grid)

| Row Labels | Pro Sales Today |
|------------|-----------------|
| SUO-MKT-001 (John) | [number input] |
| SUO-MKT-002 (Mary) | [number input] |
| SUO-MKT-003 (Peter) | [number input] |
| (Add more rows) | |

**How to create in Google Forms:**
1. Add question → Select "Multiple choice grid"
2. Rows = Marketer IDs
3. Columns = Sales numbers (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10+)

---

## Step 4: Link to Google Sheet

1. In Google Forms → **Responses** tab
2. Click green **Sheets icon**
3. Create new spreadsheet: `SuoOps Supervisor Reports - 2026`

---

## Step 5: Sheet Structure

### Tab: "Form Responses"
Auto-populated from form submissions

### Tab: "Daily Summary"
| A | B | C | D | E | F |
|---|---|---|---|---|---|
| Date | Supervisor ID | Own Sales | Team Sales | Total | Notes |

### Tab: "Marketer Breakdown"
Use formulas to extract individual marketer sales from supervisor reports:

```
=QUERY('Form Responses'!A:Z, "SELECT * WHERE B = 'SUO-SUP-001'")
```

### Tab: "Weekly Totals"
Aggregate by week for payout calculations

---

## Daily Workflow

### Marketers (By 7 PM):
```
Send to Supervisor via WhatsApp:

📊 John - Feb 4
Pro sales today: 3
Week total: 12
```

### Supervisors (By 9 PM):
```
1. Collect all team reports
2. Fill Google Form with team data
3. Done!
```

### VA (Next Morning):
```
1. Check Form Responses sheet
2. Send summary to HQ WhatsApp group
3. Follow up with missing reports
```

---

## WhatsApp Reminder Templates

### VA → Supervisors (6 PM):
```
⏰ SUPERVISOR REMINDER

Please collect your team's daily reports and submit the form by 9 PM:
👉 [FORM LINK]

Missing reports = team marked incomplete.
```

### Supervisor → Team (5 PM):
```
📊 TEAM CHECK-IN

Send me your sales for today by 7 PM:
- Your Pro signups today
- Your week total so far

Format:
"John - 3 today, 12 this week"
```

---

## Benefits of Supervisor-Only Form

| Benefit | Why |
|---------|-----|
| ✅ Fewer submissions | 3 supervisors vs 20+ marketers |
| ✅ Supervisor accountability | They must track their team |
| ✅ Cleaner data | One person per team enters data |
| ✅ Built-in verification | Supervisor confirms before submitting |
| ✅ Leadership development | Supervisors learn management |

---

## Form Access

| Role | Access |
|------|--------|
| **Marketers** | NO form access - report to supervisor |
| **Supervisors** | Form link to submit daily |
| **Sr. Supervisors** | Form link + View Sheet |
| **VA** | Full Sheet access |

---

## Sample Supervisor Form Submission

```
Date: Feb 4, 2026
Supervisor ID: SUO-SUP-001
My Sales: 2

Team:
- SUO-MKT-001 (John): 4
- SUO-MKT-002 (Mary): 3
- SUO-MKT-003 (Peter): 2

Total Team Sales: 11
Notes: Peter struggling, will mentor him tomorrow
```

---

## Weekly Verification

**Saturday: VA checks App Dashboard**

| Source | Purpose |
|--------|---------|
| Google Form data | Daily tracking & accountability |
| SuoOps App Dashboard | **TRUTH for payouts** |

If form says 50 but app shows 45 → **App wins for commission**

Form is for visibility. App is for payment.

---

**Created:** February 4, 2026  
**Version:** 2.0 (Supervisor-only reporting)
