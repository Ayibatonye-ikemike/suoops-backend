# 📊 SuoOps Marketing Team Tracker - Complete Setup Guide

## Overview

This guide creates a **fully automated system** that:
- ✅ Tracks daily sales reports from all marketers
- ✅ Auto-calculates commissions, stipends, and overrides
- ✅ Links Marketer → Supervisor → Sr. Supervisor automatically
- ✅ Cross-references with SuoOps App referral data
- ✅ Generates weekly payout reports

---

## Commission Structure Reference

| Role | Direct Commission | Override | Stipend | Bonus |
|------|------------------|----------|---------|-------|
| **Marketer** | ₦500/sale | - | ₦10,000 (if 10+ sales/week) | - |
| **Supervisor** | ₦500/sale | ₦50/team sale | ₦15,000 (if targets met) | ₦5,000 (10 active members) |
| **Sr. Supervisor** | ₦500/sale | ₦50/team + ₦25/sub-team | ₦15,000 | ₦5,000 |

---

# PART 1: CREATE THE GOOGLE SHEET (Master Database)

## Step 1.1: Create New Spreadsheet

1. Go to [sheets.google.com](https://sheets.google.com)
2. Click **+ Blank** to create new spreadsheet
3. Name it: `SuoOps Marketing Team Tracker - 2026`

---

## Step 1.2: Create Tab 1 - "Master Roster"

This is your team database. Set up once, update when team changes.

### Column Headers (Row 1):

| A | B | C | D | E | F | G | H | I | J | K | L |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Marketer ID | Full Name | Phone | Email | Referral Code | City | Role | Recruited By | Supervisor ID | Sr. Supervisor ID | Date Joined | Status |

### Data Validation Rules:

**Column G (Role):**
1. Select entire column G (except header)
2. Data → Data validation → Add rule
3. Criteria: Dropdown
4. Options: `Marketer, Supervisor, Sr. Supervisor`

**Column L (Status):**
1. Select entire column L
2. Data → Data validation → Add rule
3. Criteria: Dropdown
4. Options: `Active, Inactive, Probation, Terminated`

**Column F (City):**
1. Select entire column F
2. Data → Data validation → Add rule
3. Criteria: Dropdown
4. Options: `Lagos, Port Harcourt, Bayelsa, Abuja, Kano, Other`

### Sample Data (Rows 2-9):

```
SUO-SSR-001,Emeka Okonkwo,08012345678,emeka@email.com,REF-EEE001,Lagos,Sr. Supervisor,-,-,-,04/02/2026,Active
SUO-SUP-001,Chidi Nwosu,08023456789,chidi@email.com,REF-CCC001,Lagos,Supervisor,SUO-SSR-001,SUO-SSR-001,SUO-SSR-001,04/02/2026,Active
SUO-SUP-002,Ada Obi,08034567890,ada@email.com,REF-AAA001,Port Harcourt,Supervisor,SUO-SSR-001,SUO-SSR-001,SUO-SSR-001,04/02/2026,Active
SUO-MKT-001,John Doe,08045678901,john@email.com,REF-JJJ001,Lagos,Marketer,SUO-SUP-001,SUO-SUP-001,SUO-SSR-001,04/02/2026,Active
SUO-MKT-002,Mary Eze,08056789012,mary@email.com,REF-MMM001,Lagos,Marketer,SUO-SUP-001,SUO-SUP-001,SUO-SSR-001,04/02/2026,Active
SUO-MKT-003,Peter Okafor,08067890123,peter@email.com,REF-PPP001,Lagos,Marketer,SUO-MKT-001,SUO-SUP-001,SUO-SSR-001,04/02/2026,Active
SUO-MKT-004,Grace Udoh,08078901234,grace@email.com,REF-GGG001,Port Harcourt,Marketer,SUO-SUP-002,SUO-SUP-002,SUO-SSR-001,04/02/2026,Active
SUO-MKT-005,David Amadi,08089012345,david@email.com,REF-DDD001,Port Harcourt,Marketer,SUO-SUP-002,SUO-SUP-002,SUO-SSR-001,04/02/2026,Active
```

---

## Step 1.3: Create Tab 2 - "Form Responses"

This tab will be auto-linked to the Google Form (created in Part 2).

### Column Headers (Row 1):

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| Timestamp | Marketer ID | Full Name | Role | Date | Pro Sales Today | Week Total | Status | Notes |

### Additional Columns for Auto-Lookup (J-N):

| J | K | L | M | N |
|---|---|---|---|---|
| Supervisor ID | Sr. Supervisor ID | Recruited By | Referral Code | City |

### Formulas for Auto-Lookup (Row 2, drag down):

**J2 (Supervisor ID):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$I,9,FALSE),"-")
```

**K2 (Sr. Supervisor ID):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$J,10,FALSE),"-")
```

**L2 (Recruited By):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$H,8,FALSE),"-")
```

**M2 (Referral Code):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$E,5,FALSE),"-")
```

**N2 (City):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$F,6,FALSE),"-")
```

### Additional Columns for Supervisor Review (O-R):

| O | P | Q | R |
|---|---|---|---|
| Acknowledged? | Acknowledged By | Acknowledged Date | Supervisor Notes |

**O2 (Acknowledged?) - Add Data Validation:**
- Dropdown: `Pending, ✅ Acknowledged, ⚠️ Needs Review`
- Default: `Pending`

---

## Step 1.4: Create Tab 3 - "Weekly Summary"

This tab calculates weekly totals per person.

### Settings Row (Row 1):

| A1 | B1 | C1 | D1 |
|----|----|----|------|
| Week Start: | (Enter date) | Week End: | (Enter date) |

Example: `Week Start: 03/02/2026` and `Week End: 07/02/2026`

### Column Headers (Row 3):

| A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| Marketer ID | Name | Role | City | Week Sales | Target (10) | Target Met? |

Continue:

| H | I | J | K | L | M |
|---|---|---|---|---|---|
| Supervisor ID | Sr. Supervisor ID | Recruited By | Referral Code | App Verified Sales | Variance |

### Formulas (Row 4, after entering Marketer ID in A4):

**B4 (Name):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$B,2,FALSE),"")
```

**C4 (Role):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$G,7,FALSE),"")
```

**D4 (City):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$F,6,FALSE),"")
```

**E4 (Week Sales - from Form Responses):**
```
=SUMIFS('Form Responses'!$F:$F,'Form Responses'!$B:$B,A4,'Form Responses'!$E:$E,">="&$B$1,'Form Responses'!$E:$E,"<="&$D$1)
```

**F4 (Target):**
```
=IF(C4="Marketer",10,IF(OR(C4="Supervisor",C4="Sr. Supervisor"),5,0))
```

**G4 (Target Met?):**
```
=IF(E4>=F4,"✅ YES","❌ NO")
```

**H4 (Supervisor ID):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$I,9,FALSE),"-")
```

**I4 (Sr. Supervisor ID):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$J,10,FALSE),"-")
```

**J4 (Recruited By):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$H,8,FALSE),"-")
```

**K4 (Referral Code):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$E,5,FALSE),"-")
```

**L4 (App Verified Sales):**
- Leave blank - VA enters manually from SuoOps Dashboard

**M4 (Variance):**
```
=IF(L4="","Pending",E4-L4)
```

---

## Step 1.5: Create Tab 4 - "Commission Calculator"

This is where the magic happens - auto-calculates all payouts!

### Settings Row (Row 1):

| A1 | B1 | C1 | D1 |
|----|----|----|------|
| Week: | W1 | Week Dates: | 03/02/2026 - 07/02/2026 |

### Column Headers (Row 3):

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| Marketer ID | Name | Role | Own Sales | Own Commission | Target Met? | Stipend | L1 Team Sales | L1 Override | L2 Sub-Team Sales |

Continue:

| K | L | M | N | O | P |
|---|---|---|---|---|---|
| L2 Override | Active Members | Team Bonus | TOTAL PAYOUT | Bank Details | Payment Status |

### Formulas (Row 4):

**A4:** Enter Marketer ID manually or use:
```
='Weekly Summary'!A4
```

**B4 (Name):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$B,2,FALSE),"")
```

**C4 (Role):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$G,7,FALSE),"")
```

**D4 (Own Sales - from Weekly Summary):**
```
=IFERROR(VLOOKUP(A4,'Weekly Summary'!$A:$E,5,FALSE),0)
```

**E4 (Own Commission - ₦500 per sale):**
```
=D4*500
```

**F4 (Target Met?):**
```
=IF(AND(C4="Marketer",D4>=10),"YES",IF(AND(OR(C4="Supervisor",C4="Sr. Supervisor"),D4>=5),"YES","NO"))
```

**G4 (Stipend):**
```
=IF(AND(F4="YES",C4="Marketer"),10000,IF(AND(F4="YES",OR(C4="Supervisor",C4="Sr. Supervisor")),15000,0))
```

**H4 (L1 Team Sales - Sales by people I RECRUITED):**
```
=IF(OR(C4="Supervisor",C4="Sr. Supervisor"),SUMIF('Weekly Summary'!$J:$J,A4,'Weekly Summary'!$E:$E),0)
```

**I4 (L1 Override - ₦50 per team sale):**
```
=H4*50
```

**J4 (L2 Sub-Team Sales - Only for Sr. Supervisors):**
```
=IF(C4="Sr. Supervisor",SUMIFS('Weekly Summary'!$E:$E,'Weekly Summary'!$I:$I,A4,'Weekly Summary'!$C:$C,"<>Sr. Supervisor")-D4-H4,0)
```

**K4 (L2 Override - ₦25 per sub-team sale):**
```
=J4*25
```

**L4 (Active Team Members - people I recruited who hit target):**
```
=IF(OR(C4="Supervisor",C4="Sr. Supervisor"),COUNTIFS('Weekly Summary'!$J:$J,A4,'Weekly Summary'!$G:$G,"✅ YES"),0)
```

**M4 (Team Bonus - ₦5,000 if 10 active members):**
```
=IF(AND(OR(C4="Supervisor",C4="Sr. Supervisor"),L4>=10),5000,0)
```

**N4 (TOTAL PAYOUT):**
```
=E4+G4+I4+K4+M4
```

**O4 (Bank Details):**
```
=IFERROR(VLOOKUP(A4,'Master Roster'!$A:$D,4,FALSE),"")
```

**P4 (Payment Status):**
- Dropdown: `Pending, Processing, ✅ Paid, ❌ Failed`

---

## Step 1.6: Create Tab 5 - "Supervisor Dashboard"

Quick view for each supervisor to see their team.

### Column Headers (Row 1):

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| Supervisor ID | Supervisor Name | Team Size | Active Members | Team Week Sales | Team Target | Target Met? | Total L1 Override |

### Formulas (Row 2 - for each supervisor):

**A2:** `SUO-SUP-001` (enter manually)

**B2 (Name):**
```
=VLOOKUP(A2,'Master Roster'!$A:$B,2,FALSE)
```

**C2 (Team Size):**
```
=COUNTIF('Master Roster'!$I:$I,A2)
```

**D2 (Active Members who hit target):**
```
=COUNTIFS('Weekly Summary'!$H:$H,A2,'Weekly Summary'!$G:$G,"✅ YES")
```

**E2 (Team Week Sales):**
```
=SUMIF('Weekly Summary'!$H:$H,A2,'Weekly Summary'!$E:$E)
```

**F2 (Team Target):**
```
=C2*10
```

**G2 (Target Met?):**
```
=IF(E2>=50,"✅ YES","❌ "&E2&"/50")
```

**H2 (Total L1 Override):**
```
=E2*50
```

---

## Step 1.7: Create Tab 6 - "App Verification"

For VA to enter data from SuoOps Dashboard to verify.

### Column Headers (Row 1):

| A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| Week | Referral Code | Marketer ID | Name | App Pro Sales | Form Reported | Variance |

### Formulas:

**C2 (Marketer ID - lookup from Referral Code):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$E:$A,1,FALSE),"Not Found")
```

**D2 (Name):**
```
=IFERROR(VLOOKUP(C2,'Master Roster'!$A:$B,2,FALSE),"")
```

**F2 (Form Reported - from Weekly Summary):**
```
=IFERROR(VLOOKUP(C2,'Weekly Summary'!$A:$E,5,FALSE),0)
```

**G2 (Variance):**
```
=E2-F2
```

---

# PART 2: CREATE THE GOOGLE FORM

## Step 2.1: Create New Form

1. Go to [forms.google.com](https://forms.google.com)
2. Click **+ Blank**
3. Name it: `📊 SuoOps Daily Sales Report`

## Step 2.2: Form Settings

1. Click ⚙️ Settings
2. Under "Responses":
   - ✅ Collect email addresses (optional)
   - ✅ Limit to 1 response (turn OFF - they submit daily)
3. Under "Presentation":
   - ✅ Show progress bar
   - Confirmation message: `Thanks! Your supervisor will review your report. Keep pushing! 💪`

## Step 2.3: Add Questions

### Question 1: Marketer ID
- **Type:** Short answer
- **Required:** ✅ Yes
- **Help text:** `Your unique ID (e.g., SUO-MKT-001). Ask your supervisor if unsure.`

### Question 2: Full Name
- **Type:** Short answer
- **Required:** ✅ Yes

### Question 3: Role
- **Type:** Dropdown
- **Required:** ✅ Yes
- **Options:**
  - Marketer
  - Supervisor
  - Sr. Supervisor

### Question 4: Date
- **Type:** Date
- **Required:** ✅ Yes

### Question 5: Pro Sales Today
- **Type:** Short answer (with number validation)
- **Required:** ✅ Yes
- **Validation:** Number → Greater than or equal to → 0
- **Help text:** `How many Pro subscriptions did you close today using your referral code?`

### Question 6: Week Total So Far
- **Type:** Short answer (with number validation)
- **Required:** ✅ Yes
- **Validation:** Number → Greater than or equal to → 0
- **Help text:** `Your total Pro sales this week (Monday to today)`

### Question 7: Status
- **Type:** Dropdown
- **Required:** ✅ Yes
- **Options:**
  - 🟢 On track to hit weekly target
  - 🟡 Behind but catching up
  - 🔴 Need support

### Question 8: Notes/Challenges (Optional)
- **Type:** Paragraph
- **Required:** No
- **Help text:** `Any challenges? Wins? Support needed?`

---

## Step 2.4: Link Form to Sheet

1. In Google Forms, click **Responses** tab
2. Click the green **Sheets icon** 📊
3. Select: **Select existing spreadsheet**
4. Choose: `SuoOps Marketing Team Tracker - 2026`
5. It will create a new tab called `Form Responses 1`
6. Rename this tab to `Form Responses`

**Important:** Make sure the columns match what we set up in Step 1.3!

---

# PART 3: SET UP AUTO-CALCULATIONS

## Step 3.1: Add Array Formulas for Auto-Lookup

In the `Form Responses` tab, add these formulas in Row 1 of the auto-lookup columns:

**J1 (Supervisor ID) - Array Formula:**
```
={"Supervisor ID";ARRAYFORMULA(IF(B2:B<>"",IFERROR(VLOOKUP(B2:B,'Master Roster'!$A:$I,9,FALSE),"-"),""))}
```

**K1 (Sr. Supervisor ID) - Array Formula:**
```
={"Sr. Supervisor ID";ARRAYFORMULA(IF(B2:B<>"",IFERROR(VLOOKUP(B2:B,'Master Roster'!$A:$J,10,FALSE),"-"),""))}
```

**L1 (Recruited By) - Array Formula:**
```
={"Recruited By";ARRAYFORMULA(IF(B2:B<>"",IFERROR(VLOOKUP(B2:B,'Master Roster'!$A:$H,8,FALSE),"-"),""))}
```

These will auto-fill for every new form submission!

---

## Step 3.2: Create Auto-Populating Weekly Summary

In `Weekly Summary` tab, use this formula in A4 to auto-list all active marketers:

```
=FILTER('Master Roster'!A:A,'Master Roster'!L:L="Active")
```

Then apply the other formulas from Step 1.4 to each row.

---

## Step 3.3: Create Auto-Populating Commission Calculator

In `Commission Calculator` tab, use this in A4:

```
=FILTER('Master Roster'!A:A,'Master Roster'!L:L="Active")
```

Then apply all formulas from Step 1.5.

---

# PART 4: SET UP PERMISSIONS

## Step 4.1: Sheet Sharing

Click **Share** button and add:

| Email | Role | Access Level |
|-------|------|--------------|
| va@suoops.com | VA | **Editor** |
| admin@suoops.com | SuoOps Admin | **Editor** |
| emeka@email.com | Sr. Supervisor | **Editor** (for acknowledgment) |
| chidi@email.com | Supervisor | **Editor** (for acknowledgment) |
| ada@email.com | Supervisor | **Editor** (for acknowledgment) |

## Step 4.2: Protect Sensitive Ranges

1. Select the `Form Responses` columns A-I (form data)
2. Right-click → **Protect range**
3. Set permissions: Only VA and Admin can edit
4. Columns J-R (lookup + acknowledgment): Supervisors can edit

## Step 4.3: Create Filtered Views for Supervisors

1. Data → **Create a filter**
2. For Supervisor Chidi: Filter column J (Supervisor ID) = `SUO-SUP-001`
3. Data → Filter views → **Save as filter view** → Name: "Chidi's Team"

Now Chidi can select this view to see only his team!

---

# PART 5: WEEKLY VA WORKFLOW

## Every Saturday: Verification Process

### Step 1: Open SuoOps Admin Dashboard
```
1. Go to app.suoops.com/admin
2. Navigate to: Referral Program
3. Filter by: This week's dates
```

### Step 2: Enter App Data
```
1. Open Sheet → "App Verification" tab
2. For each referral code, enter the Pro sales from dashboard
3. Check "Variance" column for discrepancies
```

### Step 3: Resolve Discrepancies
```
If Form says 15 but App says 12:
→ App wins (it's the source of truth)
→ Update "Weekly Summary" L column with App number
→ Note discrepancy for follow-up
```

### Step 4: Finalize Payouts
```
1. Go to "Commission Calculator" tab
2. Verify all TOTAL PAYOUT amounts
3. Update Payment Status to "Processing"
4. Generate bank transfer list
5. After transfer, update to "✅ Paid"
```

---

# PART 6: PAYOUT SUMMARY

## What Gets Paid (Auto-Calculated)

| Component | Formula | Example |
|-----------|---------|---------|
| **Direct Commission** | Own Sales × ₦500 | 12 × ₦500 = ₦6,000 |
| **Stipend (Marketer)** | ₦10,000 if ≥10 sales | ₦10,000 |
| **Stipend (Supervisor)** | ₦15,000 if ≥5 sales | ₦15,000 |
| **L1 Override** | Team Sales × ₦50 | 50 × ₦50 = ₦2,500 |
| **L2 Override** | Sub-Team Sales × ₦25 | 80 × ₦25 = ₦2,000 |
| **Team Bonus** | ₦5,000 if 10 active members | ₦5,000 |

## Commission Flow Example

```
Peter (Marketer) makes 10 sales
├── Recruited By: John (SUO-MKT-001)
├── Supervisor: Chidi (SUO-SUP-001)
└── Sr. Supervisor: Emeka (SUO-SSR-001)

PAYOUTS:
┌────────────────────────────────────────────┐
│ Peter gets:                                │
│   - ₦500 × 10 = ₦5,000 (direct)           │
│   - ₦10,000 (stipend - hit target)         │
│   - TOTAL: ₦15,000                         │
├────────────────────────────────────────────┤
│ John gets (he recruited Peter):            │
│   - ₦50 × 10 = ₦500 (L1 override)          │
├────────────────────────────────────────────┤
│ Emeka gets (Sr. Supervisor):               │
│   - ₦25 × 10 = ₦250 (L2 override)          │
├────────────────────────────────────────────┤
│ Chidi gets NOTHING extra                   │
│   (He didn't recruit Peter, John did)      │
└────────────────────────────────────────────┘
```

---

# QUICK REFERENCE

## Form Link
After creating, share this link:
```
https://forms.gle/XXXXXXXXXX
```

## Daily Reminder (WhatsApp)
```
⏰ DAILY REPORT REMINDER

Submit your sales report by 8 PM:
👉 [FORM LINK]

Takes 1 minute. Your supervisor will review.
No submission = no stipend eligibility!
```

## Weekly Payout Day: Monday
```
Stipends + Overrides → Bank transfer
Direct Commission → Already in SuoOps app
```

---

# CHECKLIST ✅

| Task | Time | Done? |
|------|------|-------|
| Create Google Sheet | 5 min | ☐ |
| Set up Master Roster tab | 15 min | ☐ |
| Set up Form Responses tab with formulas | 10 min | ☐ |
| Set up Weekly Summary tab | 15 min | ☐ |
| Set up Commission Calculator tab | 20 min | ☐ |
| Set up Supervisor Dashboard tab | 10 min | ☐ |
| Set up App Verification tab | 10 min | ☐ |
| Create Google Form | 10 min | ☐ |
| Link Form to Sheet | 5 min | ☐ |
| Set up permissions | 10 min | ☐ |
| Add team members to Master Roster | 10 min | ☐ |
| Test with sample submission | 5 min | ☐ |
| Share form link with team | 2 min | ☐ |
| **TOTAL** | **~2 hours** | |

---

**Created:** February 4, 2026  
**Version:** 4.0 (Complete Auto-Calculation System)
**Document Owner:** SuoOps Operations Team
