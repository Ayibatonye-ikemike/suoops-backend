# 📊 SuoOps Marketing Team Tracker - Setup Guide

## Quick Start (5 minutes)

### Option 1: Import CSV Files (Recommended)

1. **Go to** [sheets.google.com](https://sheets.google.com)
2. **Create new spreadsheet** → Name it `SuoOps Field Marketer Team - 2026`
3. **Import each CSV file:**
   - File → Import → Upload
   - Select `marketing-team-tracker-master-roster.csv`
   - Choose "Replace current sheet"
   - Rename tab to `Master Roster`
4. **Repeat for other tabs:**
   - Click **+** to add new tab
   - File → Import → Upload each CSV
   - Rename tabs: `Weekly Sales Log`, `Stipend Calculator`

### Option 2: Copy-Paste Setup

If CSV import doesn't work, copy the data from these files directly into Google Sheets.

---

## Tab 1: Master Roster

**Purpose:** Track all team members and who recruited who

| Column | What to Enter |
|--------|---------------|
| A - Marketer ID | SUO-MKT-001, SUO-SUP-001, etc. |
| B - Full Name | Person's full name |
| C - Phone | Their phone number |
| D - Email | Their email |
| E - Referral Code | From SuoOps app (REF-XXXXXX) |
| F - City | Lagos, Port Harcourt, Bayelsa |
| G - Role | Marketer, Supervisor, Sr. Supervisor |
| H - Recruited By | Marketer ID of who brought them in (or - if none) |
| I - Supervisor ID | Who they report to |
| J - Date Joined | DD/MM/YYYY |
| K - Status | Active, Inactive, Probation, Terminated |

**Add Data Validation:**
1. Select Column G (Role) → Data → Data Validation → Dropdown:
   `Marketer, Supervisor, Sr. Supervisor`
2. Select Column K (Status) → Data → Data Validation → Dropdown:
   `Active, Inactive, Probation, Terminated`
3. Select Column F (City) → Data → Data Validation → Dropdown:
   `Lagos, Port Harcourt, Bayelsa`

---

## Tab 2: Weekly Sales Log

**Purpose:** Record weekly Pro sales per marketer (from SuoOps dashboard)

| Column | What to Enter |
|--------|---------------|
| A - Week | W1, W2, W3... |
| B - Start Date | Monday of the week |
| C - End Date | Friday of the week |
| D - Marketer ID | From Master Roster |
| E - Referral Code | Their code |
| F - City | Their city |
| G - Pro Sales | Number from SuoOps Dashboard |
| H - Target Met? | Formula: `=IF(G2>=10,"YES","NO")` |
| I - Notes | Any comments |

**How to Fill (Every Saturday):**
1. Open SuoOps Admin → Referral Program
2. Filter by this week's dates
3. For each referral code, note Pro conversions
4. Enter in column G

---

## Tab 3: Stipend Calculator

**Purpose:** Auto-calculate payouts for stipends & overrides

### Formulas to Add

Copy these formulas into Row 2 and drag down:

**F2 - Target Met?**
```
=IF(E2>=10,"YES","NO")
```

**G2 - Stipend**
```
=IF(AND(F2="YES",D2="Marketer"),10000,IF(AND(F2="YES",OR(D2="Supervisor",D2="Sr. Supervisor")),15000,0))
```

**I2 - L1 Override**
```
=H2*50
```

**K2 - L2 Override**
```
=J2*25
```

**M2 - Team Bonus**
```
=IF(AND(OR(D2="Supervisor",D2="Sr. Supervisor"),L2>=10),5000,0)
```

**N2 - TOTAL EXTRA PAY**
```
=G2+I2+K2+M2
```

### How to Calculate Team Sales

**For L1 Team Sales (Column H):**
- Look up all marketers where "Recruited By" = this person's Marketer ID
- Sum their Pro Sales

**For L2 Team Sales (Column J):**
- Only for Sr. Supervisors
- Sum Pro Sales from all marketers under sub-supervisors

---

## Weekly VA Workflow

```
EVERY SATURDAY (~30 min):

1. OPEN SUOOPS ADMIN DASHBOARD
   → Referral Program → Filter by this week

2. UPDATE WEEKLY SALES LOG
   → For each marketer, enter their Pro sales from dashboard

3. UPDATE STIPEND CALCULATOR
   → Copy marketer info from Master Roster
   → Enter Pro Sales from Weekly Sales Log
   → For supervisors: Calculate team totals

4. PROCESS PAYMENTS
   → ₦500/sale = Already paid via SuoOps app ✅
   → Stipends + Overrides = Bank transfer (from column N)
```

---

## Key Reminders

### What SuoOps App Pays Automatically
- ₦500 per Pro referral (instant)

### What You Pay via Bank Transfer
- ₦10,000 stipend (marketer hits 10+ sales)
- ₦15,000 stipend (supervisor hits target)
- ₦50 × team sales (L1 override)
- ₦25 × sub-team sales (L2 override)
- ₦5,000 bonus (supervisor with 10 active members)

### Override Rules
- **L1 Override** → Goes to WHO RECRUITED the marketer
- **L2 Override** → Goes to who recruited the supervisor
- Override is based on recruitment, NOT reporting structure

---

## Example: Calculating Overrides

**Scenario:** Peter (SUO-MKT-003) makes 8 sales this week

**Master Roster shows:**
- Peter was recruited by John (SUO-MKT-001)
- John was recruited by Chidi (SUO-SUP-001)
- Chidi was recruited by Emeka (SUO-SSR-001)

**Commission Flow:**
| Who | Gets | Amount |
|-----|------|--------|
| Peter | ₦500 × 8 = ₦4,000 | Via app (automatic) |
| John | L1 Override: 8 × ₦50 = ₦400 | Bank transfer |
| Emeka | L2 Override: 8 × ₦25 = ₦200 | Bank transfer |
| Chidi | Nothing extra | He didn't recruit Peter |

---

## Quick Reference: ID Formats

| Role | ID Format | Example |
|------|-----------|---------|
| Sr. Supervisor | SUO-SSR-XXX | SUO-SSR-001 |
| Supervisor | SUO-SUP-XXX | SUO-SUP-001 |
| Marketer | SUO-MKT-XXX | SUO-MKT-001 |

---

## Need Help?

- **SuoOps Dashboard:** [app.suoops.com/admin](https://app.suoops.com/admin)
- **Full Documentation:** See `field-marketer-incentive-program.md`

---

**Created:** February 4, 2026  
**Version:** 1.0
