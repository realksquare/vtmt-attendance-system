"""
Staff & Faculty Management Application.
Allows teachers to view hourly attendance (Window A vs B), inspect unknown faces,
execute manual overrides with custom remarks, and export Excel reports.
"""

import os
from datetime import date
import pandas as pd
from database import (
    init_db, get_registered_students, get_all_timetable_slots, SessionLocal,
    HourlyAttendance, UnknownFace, Student, manual_override_attendance
)
from config import EXPORTS_DIR
from recognition import FaceRecognizer
from burst_engine import run_burst_capture


def display_hourly_matrix():
    """Display concise attendance matrix for today."""
    db = SessionLocal()
    today = date.today()
    try:
        slots = get_all_timetable_slots()
        students = get_registered_students()

        if not students:
            print("\nNo registered students found.")
            return

        print("\n" + "="*80)
        print(f"            TODAY'S ATTENDANCE SUMMARY MATRIX ({today})")
        print("="*80)
        
        # Build slot column header
        headers = [f"L{idx+1} ({s.start_time})" for idx, s in enumerate(slots)]
        header_str = " | ".join([f"{h:<14}" for h in headers])
        
        print(f"{'ID':<10} | {'Name':<15} | {header_str}")
        print("-" * (30 + len(headers) * 17))

        for s in students:
            statuses = []
            for slot in slots:
                rec = db.query(HourlyAttendance).filter(
                    HourlyAttendance.student_id == s.student_id,
                    HourlyAttendance.date == today,
                    HourlyAttendance.slot_id == slot.slot_id
                ).first()

                st = rec.final_status if rec else "-"
                statuses.append(f"{st:<14}")
            
            row_str = " | ".join(statuses)
            print(f"{s.student_id:<10} | {s.name:<15} | {row_str}")

        print("="*80)
        print("Legend: PRESENT = Full Attendance | PARTIAL_ENTRY = First 5m | PARTIAL_EXIT = Last 5m | ABSENT / '-' = None")
        print("="*80)
    finally:
        db.close()


def review_unknown_faces():
    """Inspect unknown face records saved during burst windows."""
    db = SessionLocal()
    today = date.today()
    try:
        unknowns = db.query(UnknownFace).filter(UnknownFace.date == today).all()
        print("\n" + "="*70)
        print(f"       UNRECOGNIZED FACES AUDIT LOG ({today})")
        print("="*70)

        if not unknowns:
            print("No unknown faces logged for today.")
            return

        print(f"{'ID':<4} | {'Slot ID':<18} | {'Window':<10} | {'Time':<8} | {'Saved Image Path'}")
        print("-" * 75)
        for u in unknowns:
            print(f"{u.id:<4} | {u.slot_id:<18} | {u.window:<10} | {u.timestamp:<8} | {u.image_path}")
        print("="*70)
    finally:
        db.close()


def execute_staff_override():
    """Perform manual attendance override for a student."""
    print("\n" + "="*50)
    print("        STAFF MANUAL OVERRIDE")
    print("="*50)

    student_id = input("Enter Student ID: ").strip()
    slots = get_all_timetable_slots()

    print("\nAvailable Timetable Slots:")
    for idx, s in enumerate(slots, 1):
        print(f"  {idx}. {s.slot_id} ({s.subject})")
    
    try:
        slot_choice = int(input("Select Slot Number: ").strip())
        selected_slot = slots[slot_choice - 1].slot_id
    except (ValueError, IndexError):
        print("Invalid slot selection.")
        return

    print("\nOverride Status Options:")
    print("  1. PRESENT (Manual)")
    print("  2. ABSENT (Manual)")
    print("  3. EXCUSED / MEDICAL")
    status_choice = input("Select Status Option (1-3): ").strip()

    status_map = {
        "1": "MANUAL_PRESENT",
        "2": "MANUAL_ABSENT",
        "3": "EXCUSED"
    }
    new_status = status_map.get(status_choice, "MANUAL_PRESENT")
    remarks = input("Enter Override Reason / Note: ").strip()

    success = manual_override_attendance(student_id, selected_slot, new_status, remarks)
    if success:
        print(f"\nSUCCESS: Updated {student_id} status for {selected_slot} to '{new_status}'!")
    else:
        print("\nFAILED: Could not update attendance record.")


def export_hourly_attendance_excel():
    """Export comprehensive hourly attendance matrix to Excel."""
    db = SessionLocal()
    today = date.today()
    try:
        query = db.query(
            HourlyAttendance.date,
            HourlyAttendance.slot_id,
            HourlyAttendance.student_id,
            Student.name,
            Student.department,
            Student.year,
            HourlyAttendance.window_a_status,
            HourlyAttendance.window_a_time,
            HourlyAttendance.window_b_status,
            HourlyAttendance.window_b_time,
            HourlyAttendance.final_status,
            HourlyAttendance.remarks
        ).join(Student, HourlyAttendance.student_id == Student.student_id).all()

        if not query:
            print("\nNo hourly attendance records found to export.")
            return

        data = []
        for row in query:
            data.append({
                "Date": str(row.date),
                "Slot ID": row.slot_id,
                "Student ID": row.student_id,
                "Name": row.name,
                "Department": row.department,
                "Year": row.year,
                "First 5 Min (Win A)": row.window_a_status,
                "Win A Timestamp": row.window_a_time or "-",
                "Last 5 Min (Win B)": row.window_b_status,
                "Win B Timestamp": row.window_b_time or "-",
                "Final Combined Status": row.final_status,
                "Remarks / Overrides": row.remarks
            })

        df = pd.DataFrame(data)
        today_str = today.strftime("%Y-%m-%d")
        file_path = os.path.join(EXPORTS_DIR, f"hourly_attendance_report_{today_str}.xlsx")
        
        df.to_excel(file_path, index=False, engine='openpyxl')
        print(f"\nSUCCESS: Exported {len(data)} record(s) to: {file_path}")
    except Exception as e:
        print(f"\nError exporting to Excel: {e}")
    finally:
        db.close()


def run_manual_test_burst(recognizer: FaceRecognizer = None):
    """Run an instant 15-second test burst for demonstration purposes."""
    if recognizer is None:
        recognizer = FaceRecognizer()
    
    slots = get_all_timetable_slots()
    slot_id = slots[0].slot_id if slots else "SLOT_0900_1000"
    
    print("\nRunning Instant 15-Second Test Burst...")
    print("1. Test Window A (First 5 Mins)")
    print("2. Test Window B (Last 5 Mins)")
    win_choice = input("Select Window to Test (1 or 2): ").strip()
    window = "WINDOW_B" if win_choice == "2" else "WINDOW_A"

    run_burst_capture(recognizer, slot_id=slot_id, window=window, duration_seconds=15, show_window=True)
