# Daraga Civil Registry (PostgreSQL)

This copy of the Daraga civil registry app uses **PostgreSQL** instead of SQLite, for server / capstone deployment.

**App folder:** [daragacivilregistrymanagementsystem/](daragacivilregistrymanagementsystem/)

## Download and run

1. Clone or download this repo from GitHub.
2. Install PostgreSQL and create the database (see **daragacivilregistrymanagementsystem/README.md**).
3. Open the **`daragacivilregistrymanagementsystem`** folder.
4. Copy `.env.example` to `.env`, set `DATABASE_URL`, then run `python scripts/setup_postgres.py`.
5. Install packages (`pip install -r requirements.txt`) and start with `python app.py`.

Registry data is stored in PostgreSQL. Scans stay in `uploads/` on the server and are **not** stored on GitHub.
