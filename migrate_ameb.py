"""Add AMEB tables, invoice counter, and settings. Run once after model change."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tracker.db")

if not os.path.exists(DB_PATH):
    print("No database found. Run init_db.py first.")
    exit(0)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(project)")
cols = [row[1] for row in cursor.fetchall()]

if "billing_type" not in cols:
    cursor.execute("ALTER TABLE project ADD COLUMN billing_type VARCHAR(10) NOT NULL DEFAULT 'hourly'")
if "flat_amount" not in cols:
    cursor.execute("ALTER TABLE project ADD COLUMN flat_amount FLOAT")

# Create new tables
cursor.execute("""
    CREATE TABLE IF NOT EXISTS setting (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key VARCHAR(50) UNIQUE NOT NULL,
        value VARCHAR(200) DEFAULT ''
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_counter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        next_number INTEGER NOT NULL DEFAULT 1
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number VARCHAR(20) UNIQUE NOT NULL,
        project_id INTEGER NOT NULL REFERENCES project(id),
        issue_date DATE NOT NULL,
        client_name VARCHAR(200) DEFAULT '',
        total FLOAT NOT NULL,
        status VARCHAR(10) DEFAULT 'DUE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS ameb_entry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        timetable VARCHAR(50) NOT NULL,
        hours_worked FLOAT NOT NULL,
        hours_rounded FLOAT NOT NULL,
        project_id INTEGER NOT NULL REFERENCES project(id),
        invoice_id INTEGER REFERENCES invoice(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Seed default settings
defaults = [
    ("adb_rate", "600"),
    ("qbcc_rate", "350"),
    ("ameb_rate", "91"),
    ("adb_abn", ""),
    ("qbcc_abn", ""),
    ("ameb_abn", "42 391 277 442"),
    ("adb_phone", "0451 679 010"),
    ("qbcc_phone", "0451 679 010"),
    ("ameb_phone", "0431 828 088"),
    ("adb_address", ""),
    ("qbcc_address", ""),
    ("ameb_address", "181 Phegans Bay Road, Phegans Bay NSW 2256"),
    ("payment_bsb", "063 097"),
    ("payment_account", "4274 6923"),
    ("payment_name", "David Cashman and Dalma Demeter"),
    ("payment_terms", "Payment due within 30 days."),
    ("gst_note", "GST is not applied to this invoice."),
    ("ameb_client", "Australian Music Examinations Board, NSW"),
    ("ameb_send_to", "Shishtata Neupane <office@ameb.nsw.edu.au>"),
]

for key, value in defaults:
    cursor.execute("INSERT OR IGNORE INTO setting (key, value) VALUES (?, ?)", (key, value))

# Seed invoice counter
cursor.execute("INSERT OR IGNORE INTO invoice_counter (id, next_number) VALUES (1, 1)")

conn.commit()
conn.close()
print("Migration complete: AMEB tables, settings, and invoice counter added.")
