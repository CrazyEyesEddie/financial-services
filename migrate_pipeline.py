"""Add pipeline column to existing projects. Run once after model change."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tracker.db")

if not os.path.exists(DB_PATH):
    print("No database found. Run init_db.py first.")
    exit(0)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if column already exists
cursor.execute("PRAGMA table_info(project)")
cols = [row[1] for row in cursor.fetchall()]

if "pipeline" not in cols:
    cursor.execute("ALTER TABLE project ADD COLUMN pipeline VARCHAR(20) NOT NULL DEFAULT 'ADB'")
    conn.commit()
    print("Added 'pipeline' column. Existing projects defaulted to ADB.")
else:
    print("'pipeline' column already exists.")

conn.close()
print("Done.")
