# Daraga Civil Registry Management System (PostgreSQL)

Web application for the **Municipality of Daraga** civil registry: scan/upload certificates, run local OCR (PaddleOCR), archive records, search, staff workflows, print certification, and administration (users, backups, dashboard).

This copy stores records in **PostgreSQL** for server implementation. The original SQLite project is separate.

**Repository:** [github.com/markings199/-daragacivilregistrymanagementsystem---1-PostgreSQL](https://github.com/markings199/-daragacivilregistrymanagementsystem---1-PostgreSQL)

## Quick start (PostgreSQL)

1. Install [PostgreSQL](https://www.postgresql.org/download/windows/) and start the service.

   If PostgreSQL was installed with Scoop on this PC:

   ```powershell
   $env:Path = "$env:USERPROFILE\scoop\apps\postgresql\current\bin;$env:Path"
   pg_ctl -D "$env:USERPROFILE\scoop\apps\postgresql\current\data" start
   ```

2. Clone or download this repository, then open the **`daragacivilregistrymanagementsystem`** folder.
3. Create a virtual environment, install packages, and configure the database:

   ```bash
   cd daragacivilregistrymanagementsystem
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   python scripts/setup_postgres.py
   python app.py
   ```

4. Edit `.env` if your PostgreSQL username, password, host, or database name is different from the example.
5. Open `http://127.0.0.1:5001` in your browser.

Default login after setup: **admin** / **admin123** and **staff** / **staff123**. Change these in Administration.

To copy existing SQLite records into PostgreSQL:

```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite "C:\path\to\civil_registry.db"
```

**Folder layout** (do not move `uploads/` or `backups/`):

| Folder | Purpose |
|--------|---------|
| `app.py`, `models.py` | Application entry and database models |
| `.env` / `.env.example` | PostgreSQL `DATABASE_URL` (not committed) |
| `templates/` | HTML pages (Jinja) |
| `static/` | CSS, JavaScript, seal image |
| `ocr/` | OCR engines and form JSON (`ocr/forms/`) |
| `services/` | Backup, print, annotation, scanner |
| `scripts/` | PostgreSQL setup, SQLite migration, optional seed |
| `uploads/` | Scanned certificates (runtime data) |
| `backups/` | Automatic and restore copies (runtime data) |

> Local data (`uploads/`, `backups/`, `.env`) is created on your machine and is **not** included in Git—only the application source is published.

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

In the running app: **Administration** → **Automatic Backup**.

| Setting | Purpose |
|--------|---------|
| **Schedule On** + **Daily** | Runs every day at the time you choose (municipal priority) |
| **Office server (priority)** | Shared folder on the Daraga server, e.g. `\\DARAGA-SERVER\CivilRegistryBackups` |
| **This computer (safety copy)** | Always kept under `backups/` even if the server is offline |

You can also set the server folder in `.env`:

```
DARAGA_BACKUP_ROOT=\\DARAGA-SERVER\CivilRegistryBackups
```

When the office path is set and reachable, each daily/monthly/yearly/full backup is **copied to the server first (priority)**, with a local safety copy retained. Use **Save schedule** after entering the path — the app tests write access and can sync existing zips to the server.

Files under `backups/` are never uploaded to GitHub.

### What is safe to delete

| Location | Safe to delete? |
|----------|-----------------|
| PostgreSQL database, `uploads/`, `backups/` on your server | **Only if** you already have a ZIP backup from Administration |
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
- PostgreSQL 14+ (local or server), with a database named `daraga_civil_registry` (created by `scripts/setup_postgres.py`)
- A working Python environment with:
  - [PaddlePaddle](https://www.paddlepaddle.org.cn/) installed correctly for your OS / CPU or GPU.
  - Required Python packages from `requirements.txt`.

> **Note**: PaddleOCR depends on PaddlePaddle. If OCR initialization fails, install a compatible PaddlePaddle build following the PaddleOCR documentation for Windows.

## Installation

1. Open a terminal in the project folder:

   ```bash
   cd "c:\daragacivilregistrymanagementsystem - 1-PostgreSQL\daragacivilregistrymanagementsystem"
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

4. Copy `.env.example` to `.env` and set `DATABASE_URL` for your PostgreSQL server.

5. Create the database and tables:

   ```bash
   python scripts/setup_postgres.py
   ```

6. Install PaddlePaddle compatible with your system (if not yet installed). See the official instructions and then install `paddlepaddle` or `paddlepaddle-gpu` as needed.

## Running the web app

1. Make sure the virtual environment is activated (if you created one).
2. Start the Flask app:

   ```bash
   python app.py
   ```

3. Open your browser and navigate to:

   ```text
   http://127.0.0.1:5001
   ```

4. Workflow:
   - Select a document type (Birth / Marriage / Death).
   - Upload a clear scan/photo of the certificate.
   - Wait for local OCR to complete; an editable form appears with extracted fields.
   - Correct any mistakes and click **Confirm**.

Confirmed records are stored in **PostgreSQL**. Use **Archiving** and **Search Records** in the app to manage them.

## Notes and limitations

- OCR quality depends heavily on scan quality and alignment.
- For death certificates, some fields such as **Time of Death**, **Place of Birth**, and **Informant details** may not be reliably detected and are provided as blank fields to be filled manually.
- All OCR runs locally on your machine; the app does not send images or data to the internet.

