"""
Automated Scheduler Daemon.
Monitors working days, holidays, and hourly timetable slots to automatically
trigger 5-minute camera burst sessions for Window A (First 5 Mins) and Window B (Last 5 Mins).
"""

import time
from datetime import datetime, date
from config import (
    WORKING_DAYS, HOLIDAY_CALENDAR, DEFAULT_TIMETABLE_SLOTS, BURST_WINDOW_MINUTES
)
from database import init_db
from recognition import FaceRecognizer
from burst_engine import run_burst_capture


def is_working_day(check_date: date = None) -> bool:
    """Check if given date is a valid working day (Mon-Fri) and not a holiday."""
    if check_date is None:
        check_date = date.today()
    
    date_str = check_date.strftime("%Y-%m-%d")
    if date_str in HOLIDAY_CALENDAR:
        return False
    
    # 0 = Monday, ..., 4 = Friday
    if check_date.weekday() not in WORKING_DAYS:
        return False
    
    return True


class AttendanceScheduler:
    def __init__(self, recognizer: FaceRecognizer = None):
        self.recognizer = recognizer
        # Track triggered windows for today: set of (date_str, slot_id, window)
        self.executed_windows = set()

    def get_recognizer(self) -> FaceRecognizer:
        if self.recognizer is None:
            self.recognizer = FaceRecognizer()
        return self.recognizer

    def check_and_run(self, override_date_check: bool = False, show_window: bool = True):
        """Single check iteration over timetable slots."""
        now = datetime.now()
        today_date = now.date()
        today_str = today_date.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M")
        current_minutes = now.hour * 60 + now.minute

        if not override_date_check and not is_working_day(today_date):
            print(f"[{now.strftime('%H:%M:%S')}] Today ({today_str}) is a weekend/holiday. Scheduler idling...")
            return

        for start_str, end_str, label in DEFAULT_TIMETABLE_SLOTS:
            if "Skipped" in label:
                continue

            slot_id = f"SLOT_{start_str.replace(':', '')}_{end_str.replace(':', '')}"

            # Convert slot times to minutes from midnight
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start_mins = sh * 60 + sm
            end_mins = eh * 60 + em

            # Window A: First 5 Mins of slot (e.g. 09:00 - 09:05)
            win_a_key = (today_str, slot_id, "WINDOW_A")
            if (start_mins <= current_minutes < start_mins + BURST_WINDOW_MINUTES) and (win_a_key not in self.executed_windows):
                self.executed_windows.add(win_a_key)
                rec = self.get_recognizer()
                remaining_burst_sec = (start_mins + BURST_WINDOW_MINUTES - current_minutes) * 60
                run_burst_capture(rec, slot_id, "WINDOW_A", duration_seconds=remaining_burst_sec, show_window=show_window)

            # Window B: Middle 5 Mins of slot (e.g. 09:27 - 09:32)
            mid_start_mins = start_mins + 27
            win_b_key = (today_str, slot_id, "WINDOW_B")
            if (mid_start_mins <= current_minutes < mid_start_mins + BURST_WINDOW_MINUTES) and (win_b_key not in self.executed_windows):
                self.executed_windows.add(win_b_key)
                rec = self.get_recognizer()
                remaining_burst_sec = (mid_start_mins + BURST_WINDOW_MINUTES - current_minutes) * 60
                run_burst_capture(rec, slot_id, "WINDOW_B", duration_seconds=remaining_burst_sec, show_window=show_window)

            # Window C: Last 5 Mins of slot (e.g. 09:55 - 10:00)
            win_c_key = (today_str, slot_id, "WINDOW_C")
            if (end_mins - BURST_WINDOW_MINUTES <= current_minutes < end_mins) and (win_c_key not in self.executed_windows):
                self.executed_windows.add(win_c_key)
                rec = self.get_recognizer()
                remaining_burst_sec = (end_mins - current_minutes) * 60
                run_burst_capture(rec, slot_id, "WINDOW_C", duration_seconds=remaining_burst_sec, show_window=show_window)

    def start_scheduler_loop(self, poll_interval_sec: int = 15):
        """Continuously run scheduler loop in foreground/background."""
        init_db()
        print("\n" + "="*60)
        print("    AUTOMATED ATTENDANCE SCHEDULER STARTED")
        print("    Monitoring timetable slots, working hours, and holidays...")
        print("    Press Ctrl+C to stop.")
        print("="*60 + "\n")

        try:
            while True:
                self.check_and_run()
                time.sleep(poll_interval_sec)
        except KeyboardInterrupt:
            print("\nScheduler loop stopped by user.")
