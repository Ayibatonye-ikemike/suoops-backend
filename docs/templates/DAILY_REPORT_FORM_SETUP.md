# 📝 Daily Sales Report Form - Setup Guide

## Why Use a Form?

| Without Form | With Form |
|--------------|-----------|
| Marketers send WhatsApp messages | Marketers fill 30-second form |
| VA manually tallies from chat | Data auto-populates in Sheet |
| Supervisors ask "how's my team?" | Supervisors check Sheet anytime |
| Hard to track who didn't report | Form shows who's missing |

**Key Point:** Form is for DAILY VISIBILITY. App dashboard is still source of truth for PAYOUTS.

---

## Step 1: Create Google Form (10 minutes)

### Go to [forms.google.com](https://forms.google.com) → Click **+ Blank**

### Form Title:
```
📊 SuoOps Daily Sales Report
```

### Form Description:
```
Submit your daily sales report by 8 PM.
This takes 30 seconds and helps us track team performance!
```

---

### Add These Questions:

#### Question 1: Your Marketer ID
- **Type:** Short answer
- **Required:** Yes
- **Help text:** `Example: SUO-MKT-001 or SUO-SUP-001`

#### Question 2: Your Name
- **Type:** Short answer
- **Required:** Yes

#### Question 3: City
- **Type:** Dropdown
- **Required:** Yes
- **Options:**
  - Lagos
  - Port Harcourt
  - Bayelsa
  - Other

#### Question 4: Date
- **Type:** Date
- **Required:** Yes
- **Help text:** `Today's date`

#### Question 5: Pro Signups Today
- **Type:** Number (Short answer with number validation)
- **Required:** Yes
- **Help text:** `How many customers subscribed to Pro today using your referral code?`

#### Question 6: Running Week Total
- **Type:** Number
- **Required:** Yes
- **Help text:** `Your total Pro signups this week so far (Mon-today)`

#### Question 7: Notes (Optional)
- **Type:** Paragraph
- **Required:** No
- **Help text:** `Any challenges? Need support? Good news to share?`

---

## Step 2: Link Form to Google Sheet

1. In Google Forms, click **Responses** tab
2. Click the green **Sheets icon** (Link to Sheets)
3. Choose **"Create a new spreadsheet"**
4. Name it: `SuoOps Daily Reports - 2026`

Now every form submission automatically goes to this sheet!

---

## Step 3: Set Up Summary Views for Supervisors

### In the linked Google Sheet:

#### Create Tab: "Today's Reports"
Add this formula in A1:
```
=QUERY('Form Responses 1'!A:H, "SELECT * WHERE D = date '"&TEXT(TODAY(),"yyyy-mm-dd")&"' ORDER BY B")
```

#### Create Tab: "Team - Chidi (Lagos)"
```
=QUERY('Form Responses 1'!A:H, "SELECT * WHERE A LIKE 'SUO-MKT%' AND C = 'Lagos' ORDER BY D DESC")
```

#### Create Tab: "Team - Ada (PH)"
```
=QUERY('Form Responses 1'!A:H, "SELECT * WHERE A LIKE 'SUO-MKT%' AND C = 'Port Harcourt' ORDER BY D DESC")
```

#### Create Tab: "Weekly Summary"
| Column | Formula |
|--------|---------|
| A | Marketer ID |
| B | Name |
| C | City |
| D | `=SUMIF('Form Responses 1'!A:A, A2, 'Form Responses 1'!E:E)` (Week Total) |
| E | `=IF(D2>=10,"✅ On Track","⚠️ Behind")` |

---

## Step 4: Share Access

### For Supervisors (View Only):
1. Click **Share** → Add their email
2. Set permission: **Viewer**
3. They can see their team tab anytime!

### For VA (Edit Access):
- Full edit access to manage data

---

## Step 5: Set Up Daily Reminders

### VA WhatsApp Reminder (Send at 6 PM daily):

```
⏰ DAILY REPORT REMINDER

Team, please submit your daily report by 8 PM:
👉 [FORM LINK]

Takes 30 seconds!
Those who don't submit = marked absent.

Let's go! 💪
```

### VA Morning Update (Send at 8 AM):

```
📊 YESTERDAY'S REPORTS

Submitted: 8/10 ✅
Missing: Peter, Grace ❌

Team Total Yesterday: 25 signups
Week Total So Far: 78/100 target

Keep pushing! 🚀
```

---

## How It All Works Together

```
┌─────────────────────────────────────────────────────────┐
│                    DAILY WORKFLOW                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  9 AM - 5 PM    Marketers make sales                    │
│       ↓                                                 │
│  6 PM           VA sends WhatsApp reminder              │
│       ↓                                                 │
│  By 8 PM        Marketers submit Google Form            │
│       ↓                                                 │
│  AUTOMATIC      Data flows to Google Sheet              │
│       ↓                                                 │
│  ANYTIME        Supervisors check their team tab        │
│       ↓                                                 │
│  8 AM NEXT DAY  VA sends summary to WhatsApp groups     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## What Each Person Can See

| Role | What They Access |
|------|------------------|
| **Marketer** | Submit form only (no sheet access) |
| **Supervisor** | View their team tab in Sheet |
| **Sr. Supervisor** | View all teams in Sheet |
| **VA** | Full edit access + Admin |

---

## Tracking Who Didn't Submit

Create a "Missing Reports" tab:

```
=FILTER('Master Roster'!A:B, 
  ISERROR(MATCH('Master Roster'!A:A, 
    FILTER('Form Responses 1'!A:A, 'Form Responses 1'!D:D = TODAY()), 0)))
```

This automatically shows who hasn't submitted today!

---

## Form vs. App Dashboard

| Purpose | Source |
|---------|--------|
| **Daily visibility** | Google Form reports |
| **Supervisor team tracking** | Google Sheet (from form) |
| **Actual commission calculation** | SuoOps App Dashboard ✅ |
| **Weekly payout verification** | SuoOps App Dashboard ✅ |

**The form is for accountability. The app is for truth.**

---

## Quick Summary

| Task | Who | When |
|------|-----|------|
| Submit daily report form | All marketers | By 8 PM daily |
| Send reminder on WhatsApp | VA | 6 PM daily |
| Check team performance | Supervisors | Anytime (Sheet) |
| Verify actual sales | VA | Saturday (App Dashboard) |
| Calculate payouts | VA | Saturday (Stipend Calculator) |

---

## Form Link Template

After creating your form, the link will look like:
```
https://forms.gle/XXXXXXXXXX
```

Share this link in all WhatsApp groups!

---

**Created:** February 4, 2026  
**Version:** 1.0
