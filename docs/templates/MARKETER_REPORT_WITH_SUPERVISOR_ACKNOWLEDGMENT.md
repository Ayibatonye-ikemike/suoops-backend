# 📝 SuoOps Marketing Team Report System

## The Flow

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   MARKETER                                              │
│   Fills daily report form                               │
│        ↓                                                │
│   GOOGLE SHEET                                          │
│   Data auto-populates                                   │
│        ↓                                                │
│   SUPERVISOR                                            │
│   Reviews, acknowledges, adds feedback                  │
│        ↓                                                │
│   ALL STAKEHOLDERS CAN VIEW                             │
│   VA, SuoOps, Supervisors, Sr. Supervisors              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Who Has Access

| Role | Can Submit | Can View | Can Acknowledge | Can Edit |
|------|------------|----------|-----------------|----------|
| Marketer | ✅ Own report | ❌ | ❌ | ❌ |
| Supervisor | ✅ Own report | ✅ Their team | ✅ Their team | ✅ Add notes |
| Sr. Supervisor | ✅ Own report | ✅ All teams | ✅ All teams | ✅ Add notes |
| VA | ❌ | ✅ Everything | ✅ Everything | ✅ Full edit |
| SuoOps Admin | ❌ | ✅ Everything | ✅ Everything | ✅ Full edit |

---

## Step 1: Create the Marketer Report Form

### Go to [forms.google.com](https://forms.google.com) → Click **+ Blank**

### Form Title:
```
📊 SuoOps Daily Sales Report
```

### Form Description:
```
Submit your daily sales report by 8 PM.
Your supervisor will review and acknowledge your submission.
This takes 1 minute!
```

---

## Step 2: Form Questions

### Q1: Your Marketer ID *
- **Type:** Short answer
- **Required:** Yes
- **Help text:** `Example: SUO-MKT-001, SUO-SUP-001, or SUO-SSR-001`

### Q2: Your Full Name *
- **Type:** Short answer
- **Required:** Yes

### Q3: Your Role *
- **Type:** Dropdown
- **Required:** Yes
- **Options:**
  - Marketer
  - Supervisor
  - Sr. Supervisor

### Q4: Date *
- **Type:** Date
- **Required:** Yes

### Q5: Pro Signups Today *
- **Type:** Number
- **Required:** Yes
- **Help text:** `How many customers subscribed to Pro using your referral code today?`

### Q6: Week Total So Far *
- **Type:** Number
- **Required:** Yes
- **Help text:** `Your total Pro signups this week (Monday to today)`

### Q7: Target Status *
- **Type:** Dropdown
- **Required:** Yes
- **Options:**
  - 🟢 On track (7+ by Wed, 10+ by Fri)
  - 🟡 Behind but catching up
  - 🔴 Need support

### Q8: Challenges Today
- **Type:** Paragraph
- **Required:** No
- **Help text:** `Any difficulties? Areas you struggled with?`

### Q9: Wins Today
- **Type:** Paragraph
- **Required:** No
- **Help text:** `Good news? Breakthroughs? Tips to share?`

---

## Step 3: Link Form to Google Sheet

1. In Google Forms → Click **Responses** tab
2. Click the green **Sheets icon**
3. Create new spreadsheet: `SuoOps Marketing Team Reports - 2026`

---

## Step 4: Add Supervisor Acknowledgment Columns

In the Google Sheet, add these columns AFTER the form responses:

| J | K | L | M | N |
|---|---|---|---|---|
| Supervisor ID | Acknowledged? | Acknowledged By | Acknowledged Date | Supervisor Notes |

### Auto-fill Supervisor ID (Column J):
```
=IFERROR(VLOOKUP(B2,'Master Roster'!$A:$I,9,FALSE),"-")
```
*This pulls from Master Roster based on Marketer ID*

### Acknowledged? (Column K):
- Dropdown: `Pending, ✅ Acknowledged, ⚠️ Needs Discussion`
- Default: `Pending`

### Acknowledged By (Column L):
- Supervisor enters their name when reviewing

### Acknowledged Date (Column M):
- Date when supervisor reviewed

### Supervisor Notes (Column N):
- Feedback, coaching notes, follow-up items

---

## Step 5: Create Dashboard Views

### Tab: "Today's Reports"
```
=QUERY('Form Responses 1'!A:N, "SELECT * WHERE D = date '"&TEXT(TODAY(),"yyyy-mm-dd")&"' ORDER BY C, B")
```

### Tab: "Pending Acknowledgment"
```
=QUERY('Form Responses 1'!A:N, "SELECT * WHERE K = 'Pending' ORDER BY D DESC")
```

### Tab: "Team - [Supervisor Name]"
For each supervisor, create a filtered view:
```
=QUERY('Form Responses 1'!A:N, "SELECT * WHERE J = 'SUO-SUP-001' ORDER BY D DESC")
```

### Tab: "Weekly Summary"
| Marketer ID | Name | Mon | Tue | Wed | Thu | Fri | Week Total | Target Met? |
|-------------|------|-----|-----|-----|-----|-----|------------|-------------|

### Tab: "Supervisor Dashboard"
| Supervisor | Team Size | Reports Today | Pending Ack | Team Week Total | Target % |
|------------|-----------|---------------|-------------|-----------------|----------|

---

## Step 6: Sharing Permissions

### Google Sheet Sharing:

1. Click **Share** button
2. Add emails with appropriate access:

| Person | Access Level |
|--------|--------------|
| VA | **Editor** |
| SuoOps Admin | **Editor** |
| Sr. Supervisors | **Editor** (to acknowledge) |
| Supervisors | **Editor** (to acknowledge their team only) |

### Protect Ranges:

1. Right-click column headers → **Protect range**
2. Protect Form Response columns (A-I) from editing
3. Only allow editing of Acknowledgment columns (J-N)

---

## Step 7: Notification Setup

### Option A: Email Notifications

In Google Forms:
1. Responses → ⋮ menu → **Get email notifications**

### Option B: Sheet Notification Rules

1. Tools → **Notification rules**
2. Notify when: "Any changes are made"
3. Send to: VA email

### Option C: Slack/WhatsApp Integration (Advanced)

Use Zapier or Make.com to:
- Send new submissions to WhatsApp group
- Alert supervisor when their team member submits

---

## Daily Workflow

### Marketers (By 8 PM):
```
1. Open form link
2. Fill in: ID, Name, Date, Sales, Status
3. Submit
4. Done! (1 minute)
```

### Supervisors (By 9 PM):
```
1. Open Google Sheet
2. Filter to "Pending Acknowledgment" or your team tab
3. Review each submission
4. Update:
   - Acknowledged? → ✅ Acknowledged
   - Add your notes/feedback
5. Follow up with anyone who didn't submit
```

### VA (Next Morning):
```
1. Check "Pending Acknowledgment" tab
2. Follow up with supervisors who haven't reviewed
3. Send daily summary to HQ WhatsApp
```

---

## Sample Report Flow

### 1. John (Marketer) Submits at 7 PM:
| Field | Value |
|-------|-------|
| Marketer ID | SUO-MKT-001 |
| Name | John Doe |
| Role | Marketer |
| Date | Feb 4, 2026 |
| Pro Today | 4 |
| Week Total | 12 |
| Status | 🟢 On track |
| Challenges | Some businesses closed early |
| Wins | Got 2 referrals from existing customer! |

### 2. Chidi (Supervisor) Reviews at 8:30 PM:
| Field | Value |
|-------|-------|
| Acknowledged? | ✅ Acknowledged |
| Acknowledged By | Chidi |
| Acknowledged Date | Feb 4, 2026 |
| Supervisor Notes | Great work on referrals! Let's discuss that strategy tomorrow. |

### 3. All Stakeholders Can Now See:
- John's submission ✅
- Chidi's acknowledgment ✅
- Feedback given ✅

---

## Benefits of This System

| Benefit | Why |
|---------|-----|
| ✅ Marketer accountability | They enter their own data |
| ✅ Supervisor engagement | Must review and acknowledge |
| ✅ Two-way feedback | Supervisor can coach via notes |
| ✅ Full visibility | Everyone sees the same data |
| ✅ Audit trail | Timestamps on everything |
| ✅ Easy tracking | Filter by pending, by team, by date |

---

## Form Link Distribution

Share this with all team members:
```
📊 DAILY REPORT FORM

Submit your sales report here by 8 PM daily:
👉 [FORM LINK]

Your supervisor will review and provide feedback.
```

---

## Quick Reference

| Time | Who | Action |
|------|-----|--------|
| 8 PM | Marketers | Submit form |
| 9 PM | Supervisors | Review & acknowledge team |
| 10 PM | Sr. Supervisors | Review all teams |
| 8 AM | VA | Follow up on gaps, send summary |
| Saturday | VA | Verify with App Dashboard for payouts |

---

## Important Reminder

📱 **Form = Daily accountability & coaching**
📊 **App Dashboard = Truth for commission payouts**

If form says 15 but app shows 12 → **App wins**

---

**Created:** February 4, 2026  
**Version:** 3.0 (Marketer submit, Supervisor acknowledge)
