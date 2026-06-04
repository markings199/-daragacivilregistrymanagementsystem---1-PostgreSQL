# Daraga Civil Registry Offline System

Offline web application for the **Municipality of Daraga** civil registry: scan/upload certificates, run local OCR (PaddleOCR), archive records, search, staff workflows, print certification, and administration (users, backups, dashboard).

**Repository:** [github.com/markings199/Daraga-Civil-Registry-Offline-System](https://github.com/markings199/Daraga-Civil-Registry-Offline-System)

## Quick start (download & run)

1. Clone or download this repository (green **Code** → **Download ZIP** on GitHub).
2. Open the **`daragacivilregistrymanagementsystem`** folder (all app files are here).
3. Open a terminal in that folder:

   ```bash
   cd daragacivilregistrymanagementsystem
   ```
   *(After cloning: `cd Daraga-Civil-Registry-Offline-System/daragacivilregistrymanagementsystem`)*

4. Create a virtual environment (recommended), install dependencies, and run:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

> Local data (`civil_registry.db`, `uploads/`, `backups/`) is created on your machine and is **not** included in Git—only the application source is published.

## Backup and duplicate (safe)

Use **two kinds** of backup: **code** (GitHub) and **registry data** (your PC).

### 1. Code backup / duplicate (GitHub)

This saves the **application only** (Python, templates, CSS)—not your scanned records.

| Method | What it does |
|--------|----------------|
| **Clone** | Full copy of the repo: `git clone https://github.com/markings199/Daraga-Civil-Registry-Offline-System.git` |
| **Download ZIP** | On GitHub → **Code** → **Download ZIP** |
| **Push updates** | After changes locally: `git add .` → `git commit -m "message"` → `git push` |

### 2. Data backup (records, scans, database)

In the running app: **Administration** → **Backup & Restore** → create a **full ZIP backup** (database + uploads). Files are stored under `backups/` on your machine (never uploaded to GitHub).

You can also copy the whole project folder in File Explorer (e.g. `daragacivilregistrymanagementsystem_backup_2026-06-05`)—include `civil_registry.db`, `uploads/`, and `backups/` if you want a complete offline copy.

### What is safe to delete

| Location | Safe to delete? |
|----------|-----------------|
| `civil_registry.db`, `uploads/`, `backups/` on your PC | **Only if** you already have a ZIP backup from Administration |
| Old commits / folder experiments on GitHub | Yes—history cleanup does **not** delete files on your PC |
| Files listed in `.gitignore` | Never commit these; GitHub never had your private data |

## Features

- Offline OCR using `PaddleOCR` (no external APIs).
- Upload scanned images (`.jpg` / `.png`) of:
  - Birth Certificate
  - Marriage Certificate
  - Death Certificate
- Automatic extraction of key fields into structured forms, including:
  - Birth: Registry Number, Name of Child, Sex, Date/Place of Birth, parents' names & citizenship, Date of Marriage of Parents.
  - Marriage: Registry Number, husband & wife personal details, Date/Place of Marriage.
  - Death: Registry Number, Name of Deceased, Sex, Age, Dates, basic death details (some fields remain manual if OCR is uncertain).
- Modern, clean UI to review and correct extracted values before confirming.

## Prerequisites

- Python 3.9+ (recommended)
- A working local Python environment with:
  - [PaddlePaddle](https://www.paddlepaddle.org.cn/) installed correctly for your OS / CPU or GPU.
  - Required Python packages from `requirements.txt`.

> **Note**: PaddleOCR depends on PaddlePaddle. If OCR initialization fails, install a compatible PaddlePaddle build following the PaddleOCR documentation for Windows.

## Installation

1. Open a terminal in the project folder:

   ```bash
   cd c:\daragacivilregistrymanagementsystem
   ```

2. (Optional but recommended) Create a virtual environment:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Install PaddlePaddle compatible with your system (if not yet installed). See the official instructions and then install `paddlepaddle` or `paddlepaddle-gpu` as needed.

## Running the web app

1. Make sure the virtual environment is activated (if you created one).
2. Start the Flask app:

   ```bash
   python app.py
   ```

3. Open your browser and navigate to:

   ```text
   http://127.0.0.1:5000
   ```

4. Workflow:
   - Select a document type (Birth / Marriage / Death).
   - Upload a clear scan/photo of the certificate.
   - Wait for local OCR to complete; an editable form appears with extracted fields.
   - Correct any mistakes and click **Confirm**.

Confirmed records are stored in the local SQLite database (`civil_registry.db`). Use **Archiving** and **Search Records** in the app to manage them.

## Notes and limitations

- OCR quality depends heavily on scan quality and alignment.
- For death certificates, some fields such as **Time of Death**, **Place of Birth**, and **Informant details** may not be reliably detected and are provided as blank fields to be filled manually.
- All OCR runs locally on your machine; the app does not send images or data to the internet.

