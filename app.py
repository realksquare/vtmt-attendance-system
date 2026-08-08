"""
Smart Attendance System - Main Application Entry Point.
Interactive CLI menu unifying Enrollment, Automated Scheduler, Staff Override, and Excel Export.
"""

import sys
from database import init_db, get_registered_students
from recognition import FaceRecognizer
from enroll import enroll_student_webcam
from scheduler import AttendanceScheduler
from staff_app import (
    display_hourly_matrix, review_unknown_faces, execute_staff_override,
    export_hourly_attendance_excel, run_manual_test_burst
)


def main():
    init_db()
    recognizer = None

    while True:
        print("\n" + "="*60)
        print("     PRIVACY-PRESERVING SMART ATTENDANCE SYSTEM (FYP)")
        print("   (Automated Hourly Bursts | Dual 5-Min Windows | AES-256)")
        print("="*60)
        print("1. Enroll New Student (Webcam)")
        print("2. Start Automated Attendance Scheduler Daemon")
        print("3. Run Instant Test Burst (15s Demo)")
        print("4. View Today's Hourly Attendance Matrix")
        print("5. Review Unrecognized Unknown Face Logs")
        print("6. Execute Staff Manual Attendance Override")
        print("7. Export Hourly Attendance Report to Excel (.xlsx)")
        print("8. View All Enrolled Students")
        print("9. Exit")
        print("="*60)
        
        choice = input("Select an option (1-9): ").strip()

        if choice == "1":
            if recognizer is None:
                recognizer = FaceRecognizer()
            enroll_student_webcam(recognizer)

        elif choice == "2":
            scheduler = AttendanceScheduler(recognizer)
            scheduler.start_scheduler_loop()

        elif choice == "3":
            if recognizer is None:
                recognizer = FaceRecognizer()
            run_manual_test_burst(recognizer)

        elif choice == "4":
            display_hourly_matrix()

        elif choice == "5":
            review_unknown_faces()

        elif choice == "6":
            execute_staff_override()

        elif choice == "7":
            export_hourly_attendance_excel()

        elif choice == "8":
            students = get_registered_students()
            print("\n" + "="*50)
            print("           ENROLLED STUDENTS LIST")
            print("="*50)
            if not students:
                print("No registered students found.")
            else:
                print(f"{'Student ID':<15} | {'Name':<20} | {'Department':<15} | {'Year':<6}")
                print("-" * 65)
                for s in students:
                    print(f"{s.student_id:<15} | {s.name:<20} | {s.department:<15} | {s.year:<6}")
            print("="*50)

        elif choice == "9":
            print("\nExiting Smart Attendance System. Goodbye!")
            sys.exit(0)
        else:
            print("Invalid choice. Please enter a number between 1 and 9.")


if __name__ == "__main__":
    main()
