# Financial Services — Hour Tracker

A Flask app for tracking billable hours, originally built for Dalma at the Asian Development Bank.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize database (sets password)
python init_db.py <your-password>

# 3. Run the app
python app.py
```

Visit **http://localhost:7246** and log in with the password you set.

## Configuration

Set the port via environment variable:
```bash
export PORT=7246  # default; change to any non-obvious port
```

## Usage

1. **Projects** — Create projects (e.g., "ADB — Trade Law Review")
2. **Track** — Select a project, write what you're doing, press **Start Timer**
3. **Stop** — Press **Stop Timer** when done
4. **Dashboard** — See today's entries, total hours, and rounded days
5. **History** — View/filter past entries, export CSV or JSON
6. **Settings** — Change your password

## Rounding (Generous)

At the end of each day, total hours are rounded up to the nearest quarter-day:

| Hours Worked | Rounded Days |
|--------------|-------------|
| 0–2 hours    | 0.25 day    |
| 2–4 hours    | 0.50 day    |
| 4+ hours     | 1.00 day    |

This is intentionally generous. Thresholds can be adjusted in `app.py` (`HOURS_025` and `HOURS_05` constants).

## Export

From the History page, filter a date range and export to:
- **CSV** — For spreadsheets / ADB submission
- **JSON** — For programmatic use / future invoice generation

Future feature: per-project invoice generation (PDF).

## Tech

- **Flask 3** (Python)
- **SQLite** (single-file database in `data/tracker.db`)
- **Bootstrap 5** (Dark mode UI)
- **bcrypt** (password hashing)

## Docker

The app lives under `~/docker/financial-services/`. A Dockerfile is planned — for now, run directly:

```bash
pip install -r requirements.txt
python init_db.py <your-password>
python app.py
```
