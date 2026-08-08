"""
Burst Engine Module.
Executes automated camera burst capture for Window A (First 5 Mins) & Window B (Last 5 Mins).
Matches faces against decrypted AES templates and saves cropped images of unknown faces.
"""

import os
import time
from datetime import datetime, date
import cv2
import numpy as np

from config import (
    FRAME_WIDTH, FRAME_HEIGHT, MATCH_THRESHOLD,
    BURST_WINDOW_MINUTES, BURST_SAMPLE_INTERVAL_SEC, UNKNOWNS_DIR
)
from encrypt import get_or_create_key
from database import (
    get_all_decrypted_templates, record_window_attendance, add_unknown_face, init_db
)
from recognition import FaceRecognizer


def run_burst_capture(
    recognizer: FaceRecognizer,
    slot_id: str,
    window: str,
    duration_seconds: int = BURST_WINDOW_MINUTES * 60,
    show_window: bool = True
):
    """
    Executes automated burst capture for a lecture slot window.
    window: 'WINDOW_A' (First 5 mins) or 'WINDOW_B' (Last 5 mins).
    duration_seconds: Duration camera stays active for burst processing.
    show_window: Whether to display OpenCV video window (True for live preview, False for silent background).
    """
    init_db()
    aes_key = get_or_create_key()

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting {window} Burst Capture for Slot '{slot_id}' (Duration: {duration_seconds}s)...")
    
    # Decrypt stored templates in memory once at start of burst
    templates = get_all_decrypted_templates(aes_key)
    print(f"[{window}] Decrypted {len(templates)} enrolled student biometric template(s) in memory.")

    # Prepare unknown storage directory for today and current slot
    today_str = date.today().strftime("%Y-%m-%d")
    slot_unknown_dir = os.path.join(UNKNOWNS_DIR, today_str, slot_id, window)
    os.makedirs(slot_unknown_dir, exist_ok=True)

    # Optimize camera capture with DirectShow and MJPEG compression for smooth FPS
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print(f"ERROR [{window}]: Could not open webcam.")
        return

    start_time = time.time()
    last_sample_time = 0.0
    unknown_counter = 0
    cached_face_overlays = []
    saved_unknown_embeddings_in_window = []

    while (time.time() - start_time) < duration_seconds:
        ret, frame = cap.read()
        if not ret:
            print(f"Warning [{window}]: Failed to grab frame.")
            time.sleep(0.1)
            continue

        current_time = time.time()
        display_frame = frame.copy()
        remaining_sec = int(duration_seconds - (current_time - start_time))

        # Sample frame at configured interval (e.g. every 2 seconds)
        if (current_time - last_sample_time) >= BURST_SAMPLE_INTERVAL_SEC or not cached_face_overlays:
            last_sample_time = current_time
            faces = recognizer.detect_and_embed(frame)
            cached_face_overlays = []

            for face in faces:
                box = face.bbox.astype(int)
                embedding = face.embedding

                # Anti-Spoofing Liveness Check: Reject phone screens & printed photos
                h, w, _ = frame.shape
                x1, y1, x2, y2 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
                crop = frame[y1:y2, x1:x2]

                is_live, liveness_score, reason = recognizer.verify_liveness(crop, face)
                if not is_live:
                    print(f"  -> [{window} ANTI-SPOOF REJECTED]: {reason} (Score: {liveness_score:.1f})")
                    cached_face_overlays.append((box, f"SPOOF: {reason}", (0, 0, 255)))
                    continue

                student_id, name, score = recognizer.find_match(embedding, templates, threshold=MATCH_THRESHOLD)

                if student_id:
                    # Recognized student
                    marked = record_window_attendance(student_id, slot_id, window, score)
                    if marked:
                        print(f"  -> [{window} RECOGNIZED]: {name} ({student_id}) | Confidence: {score:.2f}")
                    cached_face_overlays.append((box, f"{name} ({score:.2f})", (0, 255, 0)))
                else:
                    # Unrecognized face logic with boundary completeness check and deduplication
                    h, w, _ = frame.shape
                    box_w = box[2] - box[0]
                    box_h = box[3] - box[1]

                    # 1. Boundary Completeness Check: Ensure face is NOT cut off at edges
                    is_fully_captured = (
                        box[0] >= 15 and box[1] >= 15 and
                        box[2] <= (w - 15) and box[3] <= (h - 15) and
                        box_w >= 60 and box_h >= 60
                    )

                    if is_fully_captured:
                        # 2. In-Window Deduplication: Check if this unknown face was already saved in this window
                        is_duplicate_unknown = False
                        for saved_emb in saved_unknown_embeddings_in_window:
                            if recognizer.cosine_similarity(embedding, saved_emb) >= MATCH_THRESHOLD:
                                is_duplicate_unknown = True
                                break

                        if not is_duplicate_unknown:
                            saved_unknown_embeddings_in_window.append(embedding)
                            unknown_counter += 1
                            x1, y1, x2, y2 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
                            crop = frame[y1:y2, x1:x2]
                            img_filename = f"unknown_{datetime.now().strftime('%H%M%S')}_{unknown_counter}.jpg"
                            img_path = os.path.join(slot_unknown_dir, img_filename)
                            cv2.imwrite(img_path, crop)
                            add_unknown_face(slot_id, window, img_path)
                            print(f"  -> [{window} UNKNOWN SAVED]: Clean crop saved to {img_path}")
                        else:
                            pass # Skip duplicate save for already recorded unknown in this window
                    else:
                        # Partial/cut-off face at edge -> do not record
                        pass

                    cached_face_overlays.append((box, f"Unknown ({score:.2f})", (0, 0, 255)))

        # Draw cached face overlays on smooth 30 FPS display frame
        for box, label, color in cached_face_overlays:
            cv2.rectangle(display_frame, (box[0], box[1]), (box[2], box[3]), color, 2)
            cv2.rectangle(display_frame, (box[0], box[1] - 22), (box[2], box[1]), color, cv2.FILLED)
            cv2.putText(display_frame, label, (box[0] + 5, box[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Render status banner on video stream window
        if show_window:
            status_text = f"AUTOMATED BURST ({window}) | Slot: {slot_id} | Time Remaining: {remaining_sec}s"
            cv2.rectangle(display_frame, (0, 0), (FRAME_WIDTH, 35), (30, 30, 30), cv2.FILLED)
            cv2.putText(display_frame, status_text, (10, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            cv2.imshow(f"Smart Attendance - Burst ({window})", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print(f"Burst window '{window}' manually interrupted.")
                break

    cap.release()
    if show_window:
        cv2.destroyAllWindows()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed {window} Burst Capture for Slot '{slot_id}'.\n")
