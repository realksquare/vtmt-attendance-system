"""
Student Enrollment Module.
Captures face from webcam, extracts embedding, encrypts using AES-256,
and stores student info + encrypted biometric template in database.
Raw face images are NOT stored after enrollment.
"""

import cv2
import numpy as np
from database import add_student_with_embedding, init_db
from encrypt import get_or_create_key
from recognition import FaceRecognizer
from config import FRAME_WIDTH, FRAME_HEIGHT


def enroll_student_webcam(recognizer: FaceRecognizer):
    """Interactively enroll a student using webcam feed."""
    init_db()
    key = get_or_create_key()

    print("\n" + "="*40)
    print("      ENROLL NEW STUDENT")
    print("="*40)
    student_id = input("Enter Student ID: ").strip()
    if not student_id:
        print("Student ID cannot be empty.")
        return

    name = input("Enter Full Name: ").strip()
    department = input("Enter Department: ").strip()
    year = input("Enter Year of Study: ").strip()

    # Optimize camera capture with DirectShow and MJPEG compression for smooth FPS
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    print("\nPosition face clearly in camera frame. Press 'SPACE' to capture face, or 'Q' to cancel.")

    captured_embedding = None
    frame_count = 0
    cached_faces = []

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break

        frame_count += 1
        display_frame = frame.copy()

        # Run model inference every 2nd frame for smooth 30 FPS UI
        if frame_count % 2 == 0 or not cached_faces:
            cached_faces = recognizer.detect_and_embed(frame)

        faces = cached_faces

        if len(faces) == 1:
            box = faces[0].bbox.astype(int)
            cv2.rectangle(display_frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
            cv2.putText(display_frame, "Face Detected - Press SPACE", (box[0], box[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        elif len(faces) > 1:
            cv2.putText(display_frame, "Multiple faces! Keep only ONE face in frame.", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        else:
            cv2.putText(display_frame, "No face detected...", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

        cv2.imshow("Enrollment - Smart Attendance System", display_frame)
        key_press = cv2.waitKey(1) & 0xFF

        if key_press == ord(' ') and len(faces) == 1:
            captured_embedding = faces[0].embedding
            print("Face captured successfully!")
            break
        elif key_press == ord('q'):
            print("Enrollment cancelled.")
            break

    cap.release()
    cv2.destroyAllWindows()

    if captured_embedding is not None:
        success = add_student_with_embedding(
            student_id=student_id,
            name=name,
            department=department,
            year=year,
            embedding=captured_embedding,
            aes_key=key
        )
        if success:
            print(f"\nSUCCESS: Student '{name}' ({student_id}) enrolled with encrypted 512-D face template!")
        else:
            print("\nFAILED: Could not save student template to database.")
