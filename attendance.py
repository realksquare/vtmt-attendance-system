"""
Real-time Live Attendance Tracking Module.
Decrypts stored face templates in memory, captures camera frames,
matches detected faces using Cosine Similarity, and logs attendance to SQLite.
"""

import cv2
import numpy as np
from database import get_all_decrypted_templates, record_attendance, init_db
from encrypt import get_or_create_key
from recognition import FaceRecognizer
from config import FRAME_WIDTH, FRAME_HEIGHT, MATCH_THRESHOLD


def run_live_attendance(recognizer: FaceRecognizer):
    """Run real-time video stream for attendance tracking."""
    init_db()
    key = get_or_create_key()
    
    print("\nDecrypting registered biometric templates in memory for matching...")
    templates = get_all_decrypted_templates(key)
    print(f"Loaded {len(templates)} enrolled biometric template(s).")

    if not templates:
        print("Warning: No registered templates found in database! Please enroll students first.")

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    print("\n" + "="*50)
    print("      LIVE ATTENDANCE TRACKING STARTED")
    print("      Press 'Q' to quit and return to main menu.")
    print("="*50 + "\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame.")
            break

        faces = recognizer.detect_and_embed(frame)
        display_frame = frame.copy()

        for face in faces:
            box = face.bbox.astype(int)
            res = recognizer.verify_face(frame, face, templates, require_challenge=False)

            if not res.quality_passed:
                label = f"QUALITY: {res.message}"
                color = (0, 165, 255) # Orange warning for quality
            elif not res.pad_passed:
                label = f"SPOOF: {res.message}"
                color = (0, 0, 255) # Red warning for spoof
            elif res.authorized and res.identity:
                label = f"{res.student_name} ({res.recognition_score:.2f})"
                color = (0, 255, 0)  # Green for authorized live face
                marked = record_attendance(res.identity, res.recognition_score)
                if marked:
                    print(f"ATTENDANCE MARKED: {res.student_name} ({res.identity}) | Confidence: {res.recognition_score:.2f}")
            else:
                label = f"Unknown ({res.recognition_score:.2f})"
                color = (0, 165, 255)

            # Draw bounding box & label
            cv2.rectangle(display_frame, (box[0], box[1]), (box[2], box[3]), color, 2)
            cv2.rectangle(display_frame, (box[0], box[1] - 25), (box[2], box[1]), color, cv2.FILLED)
            cv2.putText(display_frame, label, (box[0] + 5, box[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow("Smart Attendance System - Live Recognition", display_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Live attendance tracking stopped.")
