# 🔗 Auto-Linked Team Hierarchy System

## The Problem

If marketers manually enter supervisor IDs:
- ❌ They might enter wrong ID
- ❌ Extra work for them
- ❌ Data inconsistency

## The Solution

**Marketer enters ONLY their ID → Sheet auto-looks up their supervisor**

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                   MASTER ROSTER (Tab 1)                 │
│  Defines WHO reports to WHO (set up once)               │
├─────────────────────────────────────────────────────────┤
│  Marketer ID → Supervisor ID → Sr. Supervisor ID        │
│  SUO-MKT-001 → SUO-SUP-001  → SUO-SSR-001              │
│  SUO-MKT-002 → SUO-SUP-001  → SUO-SSR-001              │
│  SUO-MKT-003 → SUO-SUP-002  → SUO-SSR-001              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                DAILY REPORT FORM                        │
│  Marketer enters: ID, Name, Date, Sales                 │
│  (NO supervisor field needed!)                          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              FORM RESPONSES + VLOOKUP                   │
│  Sheet auto-adds: Supervisor ID, Sr. Supervisor ID      │
│  Using VLOOKUP from Master Roster                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              TEAM SUMMARIES (Auto-calculated)           │
│  Supervisor sees: Total team sales, each member's sales │
│  Sr. Supervisor sees: All sub-teams combined            │
└─────────────────────────────────────────────────────────┘
```

---

## Step 1: Master Roster Structure (UPDATED)

| A | B | C | D | E | F | G | H | I | J | K | L |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Marketer ID | Full Name | Phone | Email | Referral Code | City | Role | **Recruited By** | **Supervisor ID** | **Sr. Supervisor ID** | Date Joined | Status |

### Key Columns:
- **H (Recruited By)** = Who recruited this person (for override commission)
- **I (Supervisor ID)** = Who they report to daily
- **J (Sr. Supervisor ID)** = The top of their chain (for L2 override)

### Example Data:

| Marketer ID | Name | Role | Recruited By | Supervisor ID | Sr. Supervisor ID |
|-------------|------|------|--------------|---------------|-------------------|
| SUO-SSR-001 | Emeka | Sr. Supervisor | - | - | - |
| SUO-SUP-001 | Chidi | Supervisor | SUO-SSR-001 | SUO-SSR-001 | SUO-SSR-001 |
| SUO-SUP-002 | Ada | Supervisor | SUO-SSR-001 | SUO-SSR-001 | SUO-SSR-001 |
| SUO-MKT-001 | John | Marketer | SUO-SUP-001 | SUO-SUP-001 | SUO-SSR-001 |
| SUO-MKT-002 | Mary | Marketer | SUO-SUP-001 | SUO-SUP-001 | SUO-SSR-001 |
| SUO-MKT-003 | Peter | Marketer | SUO-MKT-001 | SUO-SUP-001 | SUO-SSR-001 |
| SUO-MKT-004 | Grace | Marketer | SUO-SUP-002 | SUO-SUP-002 | SUO-SSR-001 |
| SUO-MKT-005 | David | Marketer | SUO-SUP-002 | SUO-SUP-002 | SUO-SSR-001 |

---

## Step 2: Daily Report Form (Simplified!)

### Form Questions (Only 5!):

1. **Marketer ID** (Required) - `SUO-MKT-001`
2. **Date** (Required) - Auto-fills today
3. **Pro Signups Today** (Required) - Number
4. **Week Total So Far** (Required) - Number  
5. **Notes** (Optional) - Any comments

**That's it!** No name, no city, no supervisor - all pulled from Master Roster.

---

## Step 3: Form Responses Sheet with Auto-Lookup

### In your Form Responses sheet, add these columns:

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| Timestamp | Marketer ID | Date | Pro Today | Week Total | Notes | **Supervisor ID** | **Sr. Supervisor ID** |

### Formulas for Auto-Lookup:

**G2 (Supervisor ID):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$I,9,FALSE),"-")
```

**H2 (Sr. Supervisor ID):**
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$J,10,FALSE),"-")
```

**Drag these formulas down for all rows!**

---

## Step 4: Supervisor Team Dashboard (Auto-Calculated)

### Create Tab: "Supervisor Dashboard"

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| Supervisor ID | Supervisor Name | Team Members | Team Sales Today | Team Week Total | Target Status |

### Formulas:

**A2:** `SUO-SUP-001` (manual entry for each supervisor)

**B2 (Supervisor Name):**
```
=VLOOKUP(A2,'Master Roster'!$A:$B,2,FALSE)
```

**C2 (Team Members Count):**
```
=COUNTIF('Master Roster'!$I:$I,A2)
```

**D2 (Team Sales Today):**
```
=SUMIFS('Form Responses'!$D:$D,'Form Responses'!$G:$G,A2,'Form Responses'!$C:$C,TODAY())
```

**E2 (Team Week Total):**
```
=SUMIFS('Form Responses'!$E:$E,'Form Responses'!$G:$G,A2,'Form Responses'!$C:$C,">="&(TODAY()-WEEKDAY(TODAY(),2)+1))
```

**F2 (Target Status):**
```
=IF(E2>=50,"✅ On Track","⚠️ "&E2&"/50")
```

---

## Step 5: Sr. Supervisor Dashboard (All Sub-Teams)

### Create Tab: "Sr. Supervisor Dashboard"

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| Sr. Supervisor ID | Name | Total Supervisors | Total Marketers | All Teams Sales Today | All Teams Week Total |

### Formulas:

**C2 (Total Supervisors under them):**
```
=COUNTIFS('Master Roster'!$J:$J,A2,'Master Roster'!$G:$G,"Supervisor")
```

**D2 (Total Marketers under their supervisors):**
```
=COUNTIF('Master Roster'!$J:$J,A2)-C2-1
```

**E2 (All Teams Sales Today):**
```
=SUMIFS('Form Responses'!$D:$D,'Form Responses'!$H:$H,A2,'Form Responses'!$C:$C,TODAY())
```

**F2 (All Teams Week Total):**
```
=SUMIFS('Form Responses'!$E:$E,'Form Responses'!$H:$H,A2,'Form Responses'!$C:$C,">="&(TODAY()-WEEKDAY(TODAY(),2)+1))
```

---

## Step 6: Auto-Calculate Stipends & Overrides

### Create Tab: "Weekly Payout Calculator"

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| ID | Name | Role | Own Sales | Target Met? | Stipend | L1 Team Sales | L1 Override | L2 Team Sales | L2 Override |

Continue:
| K | L | M |
|---|---|---|
| Team Bonus | TOTAL EXTRA PAY | Recruited By (for override) |

### Key Formulas:

**D2 (Own Sales - from Form):**
```
=SUMIFS('Form Responses'!$D:$D,'Form Responses'!$B:$B,A2,'Form Responses'!$C:$C,">="&$P$1,'Form Responses'!$C:$C,"<="&$P$2)
```
*(Where P1 = Week Start Date, P2 = Week End Date)*

**G2 (L1 Team Sales - sum of people I RECRUITED):**
```
=SUMIF('Master Roster'!$H:$H,A2,D:D)
```

**I2 (L2 Team Sales - sum of sub-team sales):**
```
=IF(C2="Sr. Supervisor",SUMIFS(D:D,'Master Roster'!$J:$J,A2)-D2-G2,0)
```

**M2 (Who recruited me - for their override):**
```
=VLOOKUP(A2,'Master Roster'!$A:$H,8,FALSE)
```

---

## Complete Workflow

```
1. VA sets up Master Roster ONCE
   └→ Links: Marketer → Supervisor → Sr. Supervisor

2. Marketer fills daily form (30 sec)
   └→ Only enters: ID, Date, Sales

3. Sheet auto-populates
   └→ Supervisor ID (VLOOKUP)
   └→ Sr. Supervisor ID (VLOOKUP)

4. Dashboards auto-update
   └→ Supervisor sees their team totals
   └→ Sr. Supervisor sees all sub-teams

5. Weekly payout auto-calculates
   └→ Stipends based on Target Met
   └→ L1 Override based on recruited team
   └→ L2 Override based on sub-teams
```

---

## What Each Person Sees

| Role | Their Dashboard Shows |
|------|----------------------|
| **Marketer** | Their own submissions |
| **Supervisor** | Their direct reports' daily sales, team total |
| **Sr. Supervisor** | All supervisors' teams, combined totals |
| **VA** | Everything + payout calculations |

---

## Share Settings

| Person | Access Level | What They See |
|--------|--------------|---------------|
| Marketers | Form link only | Submit form |
| Supervisors | Viewer | Their team tab |
| Sr. Supervisors | Viewer | All teams tab |
| VA | Editor | Full sheet |

---

## Summary

✅ **Marketer fills simple form** (ID + Date + Sales)  
✅ **Sheet auto-links to supervisor** (VLOOKUP from Master Roster)  
✅ **Supervisor dashboard auto-calculates** (Team totals)  
✅ **Sr. Supervisor sees all sub-teams** (Aggregated view)  
✅ **Payouts auto-calculate** (Stipends + Overrides)  

**One-time setup, then everything flows automatically!**

---

**Created:** February 4, 2026  
**Version:** 1.0
