import sqlite3
import os
from database import init_db

print("Migrating SQLite schema for Window C columns...")
db_path = os.path.join(os.path.dirname(__file__), "database", "attendance.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()

cols = [
    ("window_c_status", "TEXT DEFAULT 'ABSENT'"),
    ("window_c_time", "TEXT DEFAULT NULL"),
    ("window_c_confidence", "REAL DEFAULT 0.0")
]

for col_name, col_def in cols:
    try:
        c.execute(f"ALTER TABLE hourly_attendance ADD COLUMN {col_name} {col_def}")
        print(f"Added column {col_name} to hourly_attendance")
    except Exception as e:
        print(f"Column {col_name} already exists or error: {e}")

conn.commit()
conn.close()

init_db()
print("Tri-window schema migration finished successfully!")
