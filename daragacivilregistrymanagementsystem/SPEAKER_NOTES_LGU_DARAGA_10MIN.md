# Speaker Notes — LGU Daraga MCR Presentation (10 Minutes Total)

**Audience:** Municipal Civil Registrar, LGU Daraga, Albay  
**Total speaking time:** 10:00 (all slides + live demo narration)  
**How to use:** Copy the **Speaker Notes** block under each slide into PowerPoint/Google Slides → *Notes* pane. Follow **On-screen** and **Actions** during the live demo slides (8–15).

| Slide | Title | Start | End | Duration |
|-------|--------|-------|-----|----------|
| 1 | Title | 0:00 | 0:25 | 0:25 |
| 2 | Background / Why | 0:25 | 0:55 | 0:30 |
| 3 | Project objectives | 0:55 | 1:35 | 0:40 |
| 4 | Scope | 1:35 | 2:05 | 0:30 |
| 5 | Security & privacy | 2:05 | 2:40 | 0:35 |
| 6 | Office workflow | 2:40 | 3:05 | 0:25 |
| 7 | Transition to live demo | 3:05 | 3:15 | 0:10 |
| 8 | Demo — Staff login | 3:15 | 3:45 | 0:30 |
| 9 | Demo — Search & view record | 3:45 | 4:45 | 1:00 |
| 10 | Demo — Print & logging | 4:45 | 5:05 | 0:20 |
| 11 | Demo — Request an edit | 5:05 | 5:50 | 0:45 |
| 12 | Demo — Scan workflow | 5:50 | 6:10 | 0:20 |
| 13 | Demo — Admin approval | 6:10 | 7:00 | 0:50 |
| 14 | Demo — Staff completes edit | 7:00 | 7:50 | 0:50 |
| 15 | Demo — Print & audit logs | 7:50 | 8:20 | 0:30 |
| 16 | Closing & thank you | 8:20 | 10:00 | 1:40 |

**Note on Slides 8–15:** These are **live demo** segments—your slide can show a screenshot or the title only while you operate the browser at http://127.0.0.1:5001. Slide 16 can stay on screen while you deliver the closing (no clicking required).

---

## SLIDE 1 — Title  
**Time: 0:00 – 0:25**

### On-screen
- Daraga Civil Registry Management System  
- Municipal Civil Registry Office — LGU Daraga, Albay  
- Presenter name / date  
- LGU or MCR seal (optional)

### Speaker notes
Good morning, Honorable Municipal Civil Registrar, Ma’am/Sir. Thank you very much for granting us this opportunity to present before you and your office.

Today we will walk you through the **Daraga Civil Registry Management System**—a tool we developed specifically for the **Municipal Civil Registry of Daraga, Albay**. In the next ten minutes, we will first cover the background and purpose of the project, then demonstrate the system live on this computer, the same way your staff would use it in the office.

Our goal is to show you how the system supports your mandate to register, keep, and release birth, marriage, and death records—securely, locally, and with clear accountability.

---

## SLIDE 2 — Background / Why this project  
**Time: 0:25 – 0:55**

### On-screen
- Vital records are still largely **paper-based**  
- Retrieval and encoding take **time** and manual reading of certificates  
- The office needs a **secure, local** solution—not cloud-based  

### Speaker notes
Every day, your office processes birth, marriage, and death documents. Much of that work still relies on **physical folders**, manual encoding, and careful reading of each certificate. When a client or an agency requests a copy, staff must locate the record, verify the details, and often re-type information by hand.

That process is correct under registry practice, but it is **slow** and heavy on staff when volume is high. At the same time, vital records contain sensitive personal information—so any digital solution must stay **inside the office**, not on the internet.

This project was undertaken to help your office **digitize** certificates, **store** them in a searchable archive, **print** with a clear record of who printed what, and **correct** errors only through a formal approval process—while keeping all data on the office computer.

---

## SLIDE 3 — Project objectives  
**Time: 0:55 – 1:35**

### On-screen
1. Digitize PSA-format certificates (local OCR — scan or upload)  
2. Archive records with scanned image + structured data  
3. Search and print with accountability  
4. Control corrections — staff request, administrator approves  
5. Operate fully **offline**  

### Speaker notes
We set five clear objectives aligned with how the civil registry actually works.

**First**, to **digitize** birth, marriage, and death certificates using **local optical character recognition**—staff scan or upload an image, and the system reads key fields into a form for review. No data is sent to external servers.

**Second**, to **archive** each record so the scanned certificate and the encoded data stay linked in one place—your digital vault on this machine.

**Third**, to let staff **search** quickly by registry number, name, document type, or date, and to **print** when needed, with a log of who printed and when.

**Fourth**, to protect data integrity: staff **cannot freely edit** archived records. They **request** a correction; the **administrator**—yourself or your designated supervisor—**reviews and approves**, and only then can staff make the change, using a one-time approval code.

**Fifth**, the entire system runs **offline** on the office PC, for privacy, reliability, and compliance with the sensitive nature of vital records.

---

## SLIDE 4 — Scope of the system  
**Time: 1:35 – 2:05**

### On-screen
| Area | Coverage |
|------|----------|
| Document types | Birth, Marriage, Death |
| Staff | Scan, encode, search, print, request edits |
| Administrator | Approve edits, users, logs, backup/restore |
| Logs | Print log, audit log |

*Footnote (small): Some death-certificate fields may require manual entry if OCR is uncertain.*

### Speaker notes
The system covers the **three vital documents** under your office: **birth**, **marriage**, and **death** certificates.

**Staff** use it for daily work: scanning or uploading new documents, reviewing OCR results, saving to the archive, searching records, printing for clients or agencies, and submitting **edit requests** when they find mistakes.

The **administrator** role is for oversight—typically the Municipal Civil Registrar or an authorized supervisor. Admins approve correction requests, manage user accounts, review print and audit logs, perform **backup and restore**, and handle permanent deletion from the archive when policy allows.

We designed the forms around **PSA-style fields** familiar to your encoders. OCR quality depends on scan clarity; staff always verify before saving, and some death fields may still be filled manually.

---

## SLIDE 5 — Security and privacy  
**Time: 2:05 – 2:40**

### On-screen
- Offline — no upload to the internet  
- Role-based access (Staff / Administrator)  
- Edit workflow: Request → Approve → One-time code → Single edit  
- Print log and audit log  
- Local database on office PC  

### Speaker notes
Because civil registry data is highly sensitive, **security and privacy** guided every design choice.

The application runs **entirely on the office computer**. Images and records are not uploaded to the cloud. Encoding, OCR, storage, and printing all happen **locally**.

**Staff** cannot silently change archived records. If a name, date, or other field is wrong—whether from OCR or human encoding—they file an **edit request** with a reason. The record stays locked until an **administrator** reviews the request against the certificate and either approves or rejects it.

On approval, the system generates a **one-time five-digit code**. Only the requesting staff member can use it, **once**, to unlock that single record for editing. After save, the code is used up.

Every **print** is logged. Important actions—logins, edits, user changes, deletions—appear in the **audit log**. The database file stays on this PC, with **backup and restore** available to administrators for disaster recovery.

This mirrors proper registry control—only in digital form, with a clear trail.

---

## SLIDE 6 — How it fits your office (workflow)  
**Time: 2:40 – 3:05**

### On-screen
```
Scan or Upload  →  OCR review  →  Archiving
                                      ↓
              Search / Print  ←  Stored record
                                      ↓
         Edit request  →  Admin approval  →  Corrected record
```

### Speaker notes
Here is how it fits your daily workflow in simple terms.

For a **new** certificate, staff scan or upload the image, the system runs **local OCR**, and staff **review and correct** the auto-filled form before confirming. The record then goes to **Archiving**—the digital vault—with the image and data stored together.

For **existing** records, staff use **Search** to find a birth, marriage, or death entry, view the certificate image beside the encoded data, and **print** when needed. Each print is logged.

If a correction is required, staff submit an **edit request**. The **administrator** verifies against the original, **approves**, and issues the **one-time code**. Staff apply the correction once; further changes require a new request and approval.

Paper records remain your legal source of truth per policy; this system supports speed, accuracy, and accountability in day-to-day operations.

---

## SLIDE 7 — Transition to live demonstration  
**Time: 3:05 – 3:15**

### On-screen
- **Live demonstration**  
- Part 1: Staff — search, print, request edit, scan  
- Part 2: Administrator — approve edit, review logs  
- Sample records pre-loaded for this session  

### Speaker notes
We will now move from the slides to a **live demonstration** on this computer.

First, we will log in as **staff** and show search, viewing a record, printing with logging, and requesting an edit. We will briefly show how **new** documents enter the system through the scan workflow.

Then we will switch to the **administrator** account to approve that edit request and show oversight through print and audit logs.

Sample records are already loaded so we can complete everything within our ten-minute schedule. Ma’am/Sir, please watch the screen.

**[Advance to Slide 8. Switch to browser: http://127.0.0.1:5001]**

---

## SLIDE 8 — Demo: Staff login and dashboard  
**Time: 3:15 – 3:45**

### On-screen (suggested)
- Screenshot: Login page — “Municipal Civil Registry of Daraga, Albay”  
- Or title only: **Live demo — Staff role**

### Actions
- Log in: username `staff`, password `staff123`  
- Point to top bar (user name, role STAFF) and sidebar menu  

### Speaker notes
Here is the **login screen** branded for the Municipal Civil Registry of Daraga. Each user signs in with their own account and role.

I am logging in now as **staff**—the role your encoders and front-desk personnel would use.

On the left you see the main menu: **Scan Workflow** for new certificates, **Archiving** for the full list of saved records, **Search Records** for quick lookup, and **My Edit Requests** where staff track correction requests they have filed.

Staff can do the everyday work of digitizing, finding, and printing records. They **do not** have permission to change archived data on their own—that stays under **administrator** control, which we will show shortly.

---

## SLIDE 9 — Demo: Search and view a record  
**Time: 3:45 – 4:45**

### On-screen (suggested)
- Screenshot: Search Records page  
- Or title: **Search & view — Birth / Marriage / Death**

### Actions
1. Open **Search Records**  
2. Select **Birth Certificate** (or Marriage / Death)  
3. Search registry number `34125-07-RE330` or a sample name  
4. Open one result  
5. Show certificate **image** and **extracted fields** side by side  

### Speaker notes
When a client, PSA, or another office needs information, staff open **Search Records**.

I will select **Birth Certificate** and search by **registry number**—here we use a sample from the archive: three-four-one-two-five, dash zero-seven, dash R-E-three-three-zero.

The system returns matching records. I will open this entry.

On the record page you see two important things together: the **scanned image of the certificate**—the same as the paper on file—and the **structured data** extracted and verified by staff: name of the child, date and place of birth, parents, registry number, and the other PSA-style fields.

This means your encoder can **verify against the image** without walking to the vault for every inquiry. Search also works by **name**, **document type**, and **event date**, depending on what the requester provides.

That is the core benefit for front-line service: **faster retrieval** with the certificate and data in one place.

---

## SLIDE 10 — Demo: Print with accountability  
**Time: 4:45 – 5:05**

### On-screen (suggested)
- Screenshot: Record detail with Print button  
- Or title: **Print — logged for accountability**

### Actions
- Click **Print** on the same record  
- Show print preview  
- **Cancel** — do not print on paper unless you intend to  

### Speaker notes
When staff need to produce a copy—for a walk-in client, a court order, or an agency request—they use **Print** from this record page.

I will open the print preview now. In actual operations, staff would print to your office printer. I will cancel here so we do not use paper during the presentation.

What matters for you as registrar is that **every print is recorded**: which user printed, which record, and **when**. That entry appears in the administrator’s **print log**, which supports accountability when certificates leave the office.

This does not replace your existing release procedures and signatures where required—it **adds a digital trail** behind each print from the system.

---

## SLIDE 11 — Demo: Request an edit  
**Time: 5:05 – 5:50**

### On-screen (suggested)
- Screenshot: Request edit form / My Edit Requests (PENDING)  
- Or title: **Controlled corrections — Edit request**

### Actions
1. On the same record, click **Request edit**  
2. Reason: *“Typo in child’s name; verified against original certificate.”*  
3. Submit  
4. Open **My Edit Requests** — show status **PENDING**  

### Speaker notes
Suppose staff notice an error—a misspelled name, wrong date, or a field that OCR misread. They **do not** click and change the archive directly.

They click **Request edit**, enter a **clear reason**—for example: “Typo in child’s name; verified against original certificate”—and submit.

The request now appears under **My Edit Requests** with status **PENDING**. The record remains **locked** until you, as administrator, review it.

This protects the **integrity of the civil registry**. Corrections follow a formal path, with the reason on record—similar in spirit to controlled amendments on paper, but tracked in the system.

In a moment we will switch to the **administrator** account and approve this same request so you can see the full cycle.

---

## SLIDE 12 — Demo: Scan workflow (new documents)  
**Time: 5:50 – 6:10**

### On-screen (suggested)
- Screenshot: Scan Workflow — document type, Upload, Scan from printer  
- Or title: **New records — Scan Workflow & offline OCR**

### Actions
- Open **Scan Workflow**  
- Select **Birth**, **Marriage**, or **Death**  
- Point to **Upload** and **Scan from printer**  
- **Do not wait** for long OCR—move on after 15–20 seconds unless it finishes instantly  

### Speaker notes
For **brand-new** documents—not yet in the archive—staff use **Scan Workflow**.

They choose the document type: **birth**, **marriage**, or **death**. They can **upload** a scanned file or use **Scan from printer** if a compatible scanner is connected to this Windows computer.

The system then runs **local OCR** on this machine—no internet—and fills a **review form**. Staff correct any mistakes, then confirm to save into **Archiving**.

First-time OCR on a PC may take one to two minutes; for today’s schedule we prepared **sample records** in advance. In daily use, staff wait for OCR, verify every field against the certificate, then save—**human verification** is always required; OCR is only an assistant.

---

## SLIDE 13 — Demo: Administrator — approve edit request  
**Time: 6:10 – 7:00**

### On-screen (suggested)
- Screenshot: Administration — Dashboard / Edit requests  
- Or title: **Administrator — Approve correction**

### Actions
1. Switch to second browser (Admin): log in `admin` / `admin123`  
2. Open **Administration** → brief glance at **Dashboard** (pending edits, counts)  
3. Go to **Edit requests**  
4. **Approve** the request from Slide 11  
5. Show the **5-digit approval code** on screen  

### Speaker notes
I will now switch to the **administrator** account—the role intended for the Municipal Civil Registrar or your authorized supervisor.

On the **Dashboard** you see an overview: pending edit requests, counts of records by type, and user management at a glance.

Under **Edit requests**, here is the pending item our staff member submitted moments ago. As administrator, you would open the record, compare the requested change against the **scanned certificate** or the paper file, and decide whether the correction is valid.

I will click **Approve**. The system generates a **one-time five-digit code**. Only the staff member who made the request can use this code, and only **once**, to unlock **this specific record** for editing.

If you **reject** the request, you may enter a reason; staff see the outcome in their request list. This keeps **you in control** of what changes enter the official digital archive.

Please note the code on screen—we will use it on the staff account next.

---

## SLIDE 14 — Demo: Staff completes edit with approval code  
**Time: 7:00 – 7:50**

### On-screen (suggested)
- Screenshot: Unlock / Use code & edit / saved record (code USED)  
- Or title: **Staff — Apply correction with one-time code**

### Actions
1. Return to **staff** browser  
2. **My Edit Requests** → **Unlock** (or **Use code & edit** on record page)  
3. Enter the 5-digit code  
4. Change one field (e.g. correct a name spelling)  
5. **Save** — show updated record; request status **USED**  

### Speaker notes
Back on the **staff** account, the encoder opens **My Edit Requests** and selects **Unlock**, or enters the code on the record page via **Use code and edit**.

They type the **five-digit code** you approved. The record opens for **one edit session**.

I will correct one field—for example, a spelling in the child’s name—then **save**.

The system updates the archived data and marks the code as **USED**. Staff cannot reuse that code. Any **further** change requires a **new request** and your **new approval**.

You retain a trail: who requested, who approved, when, and what was changed. That supports audit and discipline without blocking legitimate corrections.

---

## SLIDE 15 — Demo: Print log and audit log  
**Time: 7:50 – 8:20**

### On-screen (suggested)
- Screenshot: Administration — Print logs or Audit log  
- Or title: **Oversight — Print & audit logs**

### Actions
- In **Admin** window: open **Print logs** — point to staff print from Slide 10  
- Open **Audit log** — scroll one or two entries  
- Optionally mention **Backup/Restore** and **Users** tabs without opening them  

### Speaker notes
Under **Administration**, you have ongoing **oversight** tools.

In **Print logs**, you can see the print we demonstrated earlier—which staff user, which record, and the time. This helps when you need to answer who released a copy from the system.

The **Audit log** records significant events: logins, record edits after approval, user creation, deletions, and similar actions. Administrators can also manage **user accounts**, **backup and restore** the local database for disaster recovery, and remove records from archiving when policy allows—with those actions logged as well.

Together, these features support **accountability** and **continuity of operations** for the Municipal Civil Registry.

---

## SLIDE 16 — Closing and thank you  
**Time: 8:20 – 10:00**

### On-screen
- Summary bullets:  
  - Offline digitization (Birth, Marriage, Death)  
  - Searchable archive + print logging  
  - Corrections only with registrar/admin approval  
  - Built for LGU Daraga MCR  
- **Thank you** — questions and feedback welcome  
- Contact / next steps (optional)

### Speaker notes
Ma’am/Sir, let us close with a brief summary.

The **Daraga Civil Registry Management System** helps your office **digitize** birth, marriage, and death certificates using **offline OCR**, keep a **searchable archive** with images linked to data, **print** with a clear log, and **correct** records only through a formal process where **you or your designated administrator approves** each change with a secure one-time code.

It is designed for the **Municipal Civil Registry of Daraga, Albay**: **secure**, **local**, and aligned with how registry offices protect vital records while serving the public.

We also showed how **staff** handle encoding and front-desk tasks, and how the **administrator**—your office—maintains control through approval, logs, and backups.

We respectfully welcome your **questions**, **comments**, and guidance on what we should adjust before the system is deployed to your workstations—such as additional fields, user accounts for named staff, or training for your encoders.

Thank you again, Honorable Municipal Civil Registrar, for your time and attention. We are ready for your feedback.

**[End at 10:00. Pause for Q&A only if the program allows time beyond ten minutes.]**

---

## Master timing card (print this)

| End time | Slide | Say “…” to yourself |
|----------|-------|---------------------|
| 0:25 | 1 | Finish greeting |
| 0:55 | 2 | Finish “on the office computer” |
| 1:35 | 3 | Finish “sensitive nature of vital records” |
| 2:05 | 4 | Finish “filled manually” |
| 2:40 | 5 | Finish “clear trail” |
| 3:05 | 6 | Finish “day-to-day operations” |
| 3:15 | 7 | Say “please watch the screen” → browser |
| 3:45 | 8 | Finish “show shortly” |
| 4:45 | 9 | Finish “in one place” |
| 5:05 | 10 | Finish “from the system” |
| 5:50 | 11 | Finish “full cycle” |
| 6:10 | 12 | Finish “only an assistant” |
| 7:00 | 13 | Finish “use it on the staff account next” |
| 7:50 | 14 | Finish “legitimate corrections” |
| 8:20 | 15 | Finish “continuity of operations” |
| 10:00 | 16 | Finish “ready for your feedback” |

---

## Pre-demo checklist (before the registrar arrives)

- [ ] `python app.py` running → http://127.0.0.1:5001  
- [ ] `python seed_sample_documents.py` run once  
- [ ] Two browsers: Staff + Admin  
- [ ] Registry number `34125-07-RE330` written on a sticky note  
- [ ] Slides 1–7 advanced; browser on login page behind slides  
- [ ] Rehearse full script once with phone timer → target **9:45–10:00** at Slide 16  

---

## If you are running over time at Slide 12+

Shorten **only** these speaker notes (do not skip approval workflow):

- **Slide 12:** Say only: “New documents go through Scan Workflow—upload or scanner, local OCR, staff verify, then Archiving. We prepared samples today to save time.”  
- **Slide 15:** Say only: “Print logs and audit logs are under Administration for your review.” Do not scroll audit log.  
- **Slide 16:** Deliver the first two paragraphs only; skip the deployment/training sentence.

---

*Copy each **Speaker notes** section into your slide deck Notes pane. Daraga Civil Registry Management System — LGU Daraga, Albay.*
