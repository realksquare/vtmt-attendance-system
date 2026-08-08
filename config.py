"""
Global configuration settings for Smart Attendance System.
Includes burst timing, working hours, holiday calendar, and storage paths.
"""

import os

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_DIR = os.path.join(BASE_DIR, "keys")
DB_DIR = os.path.join(BASE_DIR, "database")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
UNKNOWNS_DIR = os.path.join(STORAGE_DIR, "unknowns")

# Ensure required directories exist
for directory in [KEYS_DIR, DB_DIR, LOGS_DIR, EXPORTS_DIR, STORAGE_DIR, UNKNOWNS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Security & DB
SECRET_KEY_PATH = os.path.join(KEYS_DIR, "secret.key")
DB_PATH = os.path.join(DB_DIR, "attendance.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Face Recognition Settings
INSIGHTFACE_MODEL_NAME = "buffalo_l"
MATCH_THRESHOLD = 0.50  # Cosine similarity threshold
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Operational & Timetable Settings
WORKING_HOURS_START = "09:00"
WORKING_HOURS_END = "17:00"
WORKING_DAYS = [0, 1, 2, 3, 4]  # Monday=0, Tuesday=1, ..., Friday=4

# 5-Minute Burst Window Settings
BURST_WINDOW_MINUTES = 5  # Duration of start/end burst
BURST_SAMPLE_INTERVAL_SEC = 2.0  # Take frame sample every 2 seconds

# Holiday Calendar (YYYY-MM-DD format)
HOLIDAY_CALENDAR = [
    "2026-01-01",  # New Year's Day
    "2026-01-26",  # Republic Day
    "2026-08-15",  # Independence Day
    "2026-10-02",  # Gandhi Jayanti
    "2026-12-25",  # Christmas
]

# Standard Hourly Timetable Slots (Start, End, Label)
DEFAULT_TIMETABLE_SLOTS = [
    ("09:00", "10:00", "Lecture 1 (09:00 - 10:00)"),
    ("10:00", "11:00", "Lecture 2 (10:00 - 11:00)"),
    ("11:00", "12:00", "Lecture 3 (11:00 - 12:00)"),
    ("12:00", "13:00", "Lunch Break (Skipped)"),
    ("13:00", "14:00", "Lecture 4 (13:00 - 14:00)"),
    ("14:00", "15:00", "Lecture 5 (14:00 - 15:00)"),
    ("15:00", "16:00", "Lecture 6 (15:00 - 16:00)"),
    ("16:00", "17:00", "Lecture 7 (16:00 - 17:00)"),
]
