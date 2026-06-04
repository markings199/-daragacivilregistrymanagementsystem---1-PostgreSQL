# Daraga Civil Registry Management System  
## 10-Minute Client Presentation — LGU Daraga, Albay  
### Municipal Civil Registry Office

**Audience:** Municipal Civil Registrar and key MCR staff  
**Total duration:** 10 minutes (strict)  
**Format:** ~3 minutes preliminaries (slides) + ~7 minutes live demo  

**Full speaker notes (every slide, timed to 10:00):** see [`SPEAKER_NOTES_LGU_DARAGA_10MIN.md`](SPEAKER_NOTES_LGU_DARAGA_10MIN.md) — copy each **Speaker notes** block into PowerPoint/Google Slides Notes.

**Ready-to-present PowerPoint:** [`Daraga_Civil_Registry_Presentation_LGU.pptx`](Daraga_Civil_Registry_Presentation_LGU.pptx) (16 slides, speaker notes included). Presenters: Mark Jhon M. Guillermo, Rod B. Rañola, Vincent S. Macauyam. Regenerate: `python build_presentation_pptx.py`

**System URL (during demo):** http://127.0.0.1:5001  

---

## Quick timing overview

| Time | Section |
|------|---------|
| 0:00–3:00 | Preliminaries (slides) |
| 3:00–9:30 | Live system demonstration |
| 9:30–10:00 | Closing and Q&A handoff |

---

# PART A — PRELIMINARIES (Slides, ~3 minutes)

Use **6–7 slides**. Speak clearly and avoid technical jargon. One slide ≈ 25–30 seconds.

---

### Slide 1 — Title (0:00 – 0:20)

**On screen:**
- **Daraga Civil Registry Management System**
- Municipal Civil Registry Office — LGU Daraga, Albay
- [Your name / team / date]
- LGU seal (if available)

**Say:**

> Good [morning/afternoon], [Honorable Municipal Civil Registrar / Ma’am/Sir ___________].  
> Thank you for your time. In the next ten minutes, we will briefly introduce the system we developed for your office, then show it working on this computer—exactly as your staff would use it day to day.

---

### Slide 2 — Why this project (0:20 – 0:50)

**On screen — bullet points:**
- Vital records (Birth, Marriage, Death) are still largely **paper-based**
- Retrieval, encoding, and corrections take **time** and rely on **manual** reading of certificates
- The office needs a **secure, local** tool—not cloud-based—to support daily registry work

**Say:**

> The Municipal Civil Registry handles birth, marriage, and death documents every day. Much of that work still depends on physical files and manual encoding. This project aims to help your office **digitize**, **store**, **search**, and **correct** records more efficiently—while keeping all data **on the office computer**, not on the internet.

---

### Slide 3 — Project objectives (0:50 – 1:25)

**On screen:**
1. **Digitize** PSA-format certificates using **local OCR** (scan or upload)
2. **Archive** records with linked scanned images and structured data
3. **Search and print** with accountability (who printed what, and when)
4. **Control corrections** through staff requests and **registrar/admin approval**
5. Operate **fully offline** for data privacy and reliability

**Say:**

> Our objectives align with how your office actually works: encode from the certificate, keep a digital archive, find records quickly when clients or agencies request them, print when needed with a clear log, and change data only through an approved process—so the registry remains accurate and auditable.

---

### Slide 4 — Scope of the system (1:25 – 1:55)

**On screen:**

| In scope | Document types |
|----------|----------------|
| Scan / upload + OCR | Birth, Marriage, Death certificates |
| Digital archive & search | Same three types |
| User roles | **Staff** (daily operations), **Administrator** (oversight & approval) |
| Reports / logs | Print log, audit log, backup & restore (admin) |

**Optional footnote:** OCR quality depends on scan clarity; some death-certificate fields may need manual entry.

**Say:**

> The system covers the three vital documents your office registers—birth, marriage, and death. Staff use it for scanning, encoding, search, and print requests. The administrator role—typically you or your designated supervisor—approves corrections, reviews activity, and manages users and backups.

---

### Slide 5 — Security and privacy (1:55 – 2:25)

**On screen:**
- **Offline operation** — no upload to external servers
- **Role-based access** — staff cannot freely edit archived records
- **Edit workflow** — request → admin approval → one-time code → single edit session
- **Print log** and **audit log** for accountability
- **Local database** on the office PC (`civil_registry.db`)

**Say:**

> Because these are sensitive personal records, everything runs **locally** on the office machine. Staff cannot silently change archived data; they must request an edit, and an administrator approves it and issues a **one-time code**. Printing and important actions are logged so the office can trace who did what and when.

---

### Slide 6 — How it fits your office (2:25 – 2:50)

**On screen — simple flow diagram (optional):**

```
Scan/Upload → OCR review → Archiving → Search / Print
                              ↓
                    Edit request → Admin approval → Corrected record
```

**Say:**

> In practice, a certificate is scanned or uploaded, the system reads key fields with OCR, staff verify and save to the archive. Later, anyone authorized can search and print. If something must be corrected, staff file a request and the administrator approves it—mirroring proper registry control, but in digital form.

---

### Slide 7 — Transition to demo (2:50 – 3:00)

**On screen:**
- **Live demonstration**
- Staff role → Administrator role
- Sample records already loaded for speed

**Say:**

> We will now show the live system. First, how **staff** search, print, and request corrections; then how the **administrator** approves edits and reviews logs. The demo uses sample records so we stay within our ten-minute schedule.

**[Switch from slides to browser.]**

---

# PART B — LIVE DEMO (~7 minutes)

## Before the presentation (not during the 10 minutes)

1. **Start the application:**
   ```powershell
   cd c:\daragacivilregistrymanagementsystem
   .\.venv\Scripts\Activate.ps1
   python app.py
   ```
2. **Load sample records** (so Search works instantly):
   ```powershell
   python seed_sample_documents.py
   ```
3. Open **two browser windows**: normal window = Staff; Incognito (or second profile) = Admin.
4. Test login once; close extra tabs.
5. Have one **registry number** ready from sample data, e.g. `34125-07-RE330` (birth) or any name from Archiving.

| Role  | Username | Password   |
|-------|----------|------------|
| Staff | `staff`  | `staff123` |
| Admin | `admin`  | `admin123` |

---

### Demo 1 — Staff login and dashboard (3:00 – 3:30)

**Screen:** Login → Dashboard (`staff`)

**Do:** Log in as Staff. Point to sidebar: Scan Workflow, Archiving, Search Records, My Edit Requests.

**Say:**

> This is the staff view—the same interface your encoders and front desk would use daily. They can scan new certificates, browse the archive, search records, and track their edit requests. They do **not** have open access to change archived data without approval.

---

### Demo 2 — Search and view a record (3:30 – 4:30)

**Screen:** **Search Records**

**Do:**
1. Select **Birth Certificate** (or Marriage / Death).
2. Search by registry number `34125-07-RE330` or a sample name.
3. Open one result.
4. Show **scanned certificate** beside **extracted fields**.

**Say:**

> When a client or agency needs a copy, staff search by registry number, name, document type, or date. Each record keeps the **image of the certificate** linked to the **encoded data** from OCR—so staff can verify against the original without pulling the physical folder first.

---

### Demo 3 — Print with accountability (4:30 – 4:50)

**Screen:** Record detail

**Do:** Click **Print** → show preview → cancel (do not waste paper).

**Say:**

> Every print is logged—who printed, which record, and when. That supports your office’s accountability, especially when certificates are released to the public.

---

### Demo 4 — Request an edit (4:50 – 5:40)

**Screen:** **Request edit** → **My Edit Requests**

**Do:**
1. On the same record, click **Request edit**.
2. Reason: *“Typo in child’s name; verified against original certificate.”*
3. Submit → open **My Edit Requests** → show **PENDING**.

**Say:**

> If staff find an error—from OCR or encoding—they do **not** edit the vault directly. They submit a request with a reason. The record stays locked until you, as administrator, review and approve. This protects the integrity of the civil registry.

---

### Demo 5 — Scan workflow (brief) (5:40 – 6:00)

**Screen:** **Scan Workflow**

**Do:** Select document type → show **Upload** and **Scan from printer** options. If a pre-scanned image is ready, upload it; **if OCR is slow, do not wait**—use the script line below.

**Say:**

> For **new** documents, staff choose birth, marriage, or death, then scan or upload. **Local OCR** fills a review form; staff correct mistakes and confirm to **Archiving**. Processing stays on this PC—no internet. On first run, OCR may take a minute or two; for today we used pre-loaded samples to keep the demo on time.

---

### Demo 6 — Administrator: approve edit (6:00 – 6:50)

**Screen:** Switch to Admin window → **Administration** → **Edit requests**

**Do:**
1. Log in as `admin`.
2. Briefly point at **Dashboard** (pending requests, record counts).
3. **Approve** the staff request from Demo 4.
4. Show the **5-digit approval code**.

**Say:**

> As Municipal Civil Registrar—or your designated admin—you see pending correction requests here. After verifying against the physical or scanned certificate, you approve and the system issues a **one-time five-digit code**. Only the staff member who requested the edit can use that code, once, to unlock that record.

---

### Demo 7 — Staff completes edit (6:50 – 7:40)

**Screen:** Staff window → **My Edit Requests** or record page

**Do:**
1. **Unlock** with the code (or **Use code & edit**).
2. Change one visible field (e.g. correct spelling in a name).
3. Save → show updated record; status **USED**.

**Say:**

> Staff enter the code, make the correction, and save. The code is then consumed—any further change requires a new request and your approval again. The system retains the trail of who requested, who approved, and what was changed.

---

### Demo 8 — Oversight: print log or audit (7:40 – 8:15)

**Screen:** Administration → **Print logs** or **Audit log**

**Do:** Show the print from Demo 3, or scroll one or two audit entries.

**Say:**

> You can review **print logs** and the **audit log** for user actions, edits, and deletions. Administrators also manage user accounts, **backup and restore** the database, and—when necessary—remove records from archiving under controlled conditions.

---

### Demo 9 — Archiving overview (optional if time) (8:15 – 8:45)

**Screen:** **Archiving**

**Do:** Scroll the list; filter by Birth / Marriage / Death if the UI supports it.

**Say:**

> All confirmed records appear in **Archiving**—your office’s digital vault on this machine. This replaces hunting through stacks of folders for routine lookup, while you still maintain official paper records per law and policy.

**If behind schedule:** Skip this scene; mention Archiving in the closing only.

---

# PART C — CLOSING (~30 seconds)

**Screen:** Login page with Daraga MCR branding, or Dashboard

**Say (9:30 – 10:00):**

> To summarize: this system helps the **Municipal Civil Registry of Daraga** digitize birth, marriage, and death certificates with **offline OCR**, keep a **searchable archive**, **print with logs**, and **correct data only through your approval**. It is built for your office’s workflow—secure, local, and accountable.  
> Thank you, [Ma’am/Sir]. We welcome your questions and feedback on what we should refine before deployment to your workstations.

**[Stop at 10:00. Offer Q&A only if the schedule allows beyond 10 minutes.]**

---

## Slide deck checklist (copy to PowerPoint / Google Slides)

| # | Slide title | ~Seconds |
|---|-------------|----------|
| 1 | Title — Daraga Civil Registry Management System | 20 |
| 2 | Background / challenge | 30 |
| 3 | Project objectives | 35 |
| 4 | Scope (Birth, Marriage, Death + roles) | 30 |
| 5 | Security & privacy (offline, approval workflow) | 30 |
| 6 | Office workflow diagram | 25 |
| 7 | Live demonstration (transition) | 10 |

**Design tips for the registrar:**
- Use LGU Daraga / MCR seal on title and closing slides
- Large fonts (24pt+ body); minimal text per slide
- Screenshot of the real login page on Slide 7 optional
- Avoid code, framework names (Flask, PaddleOCR) unless asked in Q&A

---

## If you run out of time

**Cut in this order:**
1. Demo 5 (Scan Workflow) — describe in one sentence during closing  
2. Demo 9 (Archiving browse)  
3. Demo 3 (Print) — mention logging without opening print preview  
4. Shorten Slide 6 (workflow diagram)

**Never cut for the registrar:**
- Objectives + offline/security (Slides 3 & 5)  
- Search and view record (Demo 2)  
- Request edit → Admin approve → Staff edit with code (Demos 4, 6, 7)  
- Closing summary  

---

## Anticipated questions (prepare 1-line answers)

| Question | Short answer |
|----------|----------------|
| Is data sent online? | No. OCR and storage are entirely on the office PC. |
| Who can delete records? | Administrators only; actions are audit-logged. |
| What if OCR is wrong? | Staff correct on the review form before saving; later changes need your approval. |
| Can we use our existing scanner? | Yes, on Windows via Scan from printer (WIA-supported devices). |
| Multiple computers? | Current build is single-PC (SQLite). Network/multi-user can be a future phase. |
| PSA compliance? | Forms follow PSA-style fields; official legal compliance is your office’s policy layer. |

---

## Presenter reminders

- Address the registrar respectfully (**Honorable**, **Ma’am/Sir**, **Municipal Civil Registrar**).
- Emphasize **their control** (approval codes, logs, backups)—not IT features.
- Speak in clear English; mix Filipino for courtesy if that is your office norm.
- Rehearse once with a timer: **3 min slides + 7 min demo = 10 min**.
- Keep the mouse movement slow; narrate every click.
- Do not apologize for technology—frame OCR as an **assistant** that staff always verify.

---

*Daraga Civil Registry Management System — LGU Daraga, Albay — Client presentation guide (10 minutes)*
