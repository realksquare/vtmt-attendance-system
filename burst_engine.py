"""
Burst Engine Module.
Executes classroom-wide automated camera burst capture for Window A (First 5m), Window B (Mid 5m), & Window C (Last 5m).
Features:
- Decoupled threaded camera capture buffer for responsive 30-60 FPS UI.
- 3-Tier Face Quality hierarchy (RECOGNITION_SAFE, TRACKABLE_BUT_SMALL, UNUSABLE).
- Classroom multi-student spatial-temporal face tracking (ClassroomFaceTracker).
- Burst-level multi-observation candidate identity voting and MiniFASNet PAD aggregation.
- Atomic single-transaction attendance commit at the conclusion of the burst window.
"""

import os
import time
import threading
from datetime import datetime, date
from typing import Optional, List, Tuple
import cv2
import numpy as np

from config import (
    FRAME_WIDTH, FRAME_HEIGHT, MATCH_THRESHOLD, PAD_SCORE_THRESHOLD,
    BURST_WINDOW_MINUTES, BURST_SAMPLE_INTERVAL_SEC, UNKNOWNS_DIR
)
from encrypt import get_or_create_key
from database import (
    get_all_decrypted_templates, record_window_attendance, add_unknown_face, init_db,
    SessionLocal, Student
)
from recognition import FaceRecognizer
from liveness.quality import FaceQualityAnalyzer, QualityTier, QualityResult
from liveness.pad_engine import AntiSpoofEngine, PADResult
from liveness.tracker import ClassroomFaceTracker, BurstDecisionAggregator, FaceObservation


class ThreadedCamera:
    """
    Decoupled background camera acquisition thread.
    Maintains a non-blocking latest-frame buffer to prevent OpenCV UI freezing.
    """

    def __init__(self, src: int = 0, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT, fps: int = 30):
        # Attempt DirectShow backend first, fallback to default
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = cv2.VideoCapture(src)

        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)

        self.lock = threading.Lock()
        self.running = False
        self.frame = None
        self.ret = False
        self.thread = None

    def start(self) -> bool:
        if not self.cap.isOpened():
            return False
        self.ret, self.frame = self.cap.read()
        if not self.ret or self.frame is None:
            return False

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return True

    def _capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.ret = ret
                    self.frame = frame
            else:
                time.sleep(0.01)

    def read_latest(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self.lock:
            if not self.ret or self.frame is None:
                return False, None
            return True, self.frame.copy()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap.isOpened():
            self.cap.release()


def run_burst_capture(
    recognizer: FaceRecognizer,
    slot_id: str,
    window: str,
    duration_seconds: int = BURST_WINDOW_MINUTES * 60,
    show_window: bool = True
):
    """
    Executes classroom-wide automated burst capture for a lecture slot window.
    window: 'WINDOW_A' (First 5m), 'WINDOW_B' (Mid 5m), or 'WINDOW_C' (Last 5m).
    duration_seconds: Duration camera stays active for burst processing.
    show_window: Whether to display OpenCV video window.
    """
    init_db()
    aes_key = get_or_create_key()

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting {window} Classroom Burst Capture for Slot '{slot_id}' (Duration: {duration_seconds}s)...")

    # 1. Decrypt enrolled student biometric templates once into memory
    templates = get_all_decrypted_templates(aes_key)
    enrolled_student_ids = [t[0] for t in templates]
    print(f"[{window}] Decrypted {len(templates)} enrolled student biometric template(s) in memory.")

    # 2. Prepare unknowns directory
    today_str = date.today().strftime("%Y-%m-%d")
    slot_unknown_dir = os.path.join(UNKNOWNS_DIR, today_str, slot_id, window)
    os.makedirs(slot_unknown_dir, exist_ok=True)

    # 3. Start Decoupled Threaded Camera
    camera = ThreadedCamera(src=0, width=FRAME_WIDTH, height=FRAME_HEIGHT, fps=30)
    if not camera.start():
        print(f"ERROR [{window}]: Could not open webcam.")
        return

    # 4. Initialize Multi-Face Tracker and Quality Analyzer
    tracker = ClassroomFaceTracker(iou_threshold=0.25, max_centroid_dist=120.0)
    quality_analyzer = recognizer.quality_analyzer
    pad_engine = recognizer.pad_engine

    window_name = f"Smart Attendance - Classroom Burst ({window})"
    if show_window:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, FRAME_WIDTH, FRAME_HEIGHT)
        try:
            cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
        except Exception:
            pass

    start_time = time.time()
    last_sample_time = 0.0
    active_hud_overlays = []

    try:
        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            if elapsed >= duration_seconds:
                break

            ret, frame = camera.read_latest()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            display_frame = frame.copy()
            remaining_sec = max(0, int(duration_seconds - elapsed))

            # Sample inference at controlled interval (e.g. every 0.4s) while displaying at 60 FPS
            if (current_time - last_sample_time) >= BURST_SAMPLE_INTERVAL_SEC:
                last_sample_time = current_time
                faces = recognizer.detect_and_embed(frame)
                current_observations = []

                for face in faces:
                    box = face.bbox.astype(int)
                    embedding = face.embedding

                    # 1. 3-Tier Face Quality Assessment
                    q_res = quality_analyzer.assess_face(frame, face)

                    # Crop face region
                    h, w, _ = frame.shape
                    cx1, cy1, cx2, cy2 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
                    crop_img = frame[cy1:cy2, cx1:cx2].copy() if (cx2 > cx1 and cy2 > cy1) else None

                    # 2. Passive MiniFASNet PAD Inference
                    pad_res = None
                    if q_res.tier != QualityTier.UNUSABLE:
                        pad_res = pad_engine.verify(frame, box)

                    # 3. Independent Face Recognition Candidate Match
                    matched_id = None
                    matched_name = None
                    best_score = 0.0

                    if q_res.tier == QualityTier.RECOGNITION_SAFE and embedding is not None:
                        matched_id, matched_name, best_score = recognizer.find_match(embedding, templates)

                    obs = FaceObservation(
                        timestamp=current_time,
                        bbox=box,
                        quality_res=q_res,
                        pad_res=pad_res,
                        embedding=embedding,
                        matched_id=matched_id,
                        matched_name=matched_name,
                        similarity=best_score,
                        crop_image=crop_img
                    )
                    current_observations.append(obs)

                # Update Multi-Face Tracker
                matched_tracks = tracker.update(current_observations)

                # Build HUD overlays for real-time visual feedback
                active_hud_overlays = []
                for track_id, obs in matched_tracks:
                    box = obs.bbox
                    tier = obs.quality_res.tier
                    if tier == QualityTier.UNUSABLE:
                        label = f"T#{track_id}: Poor Quality"
                        color = (0, 165, 255) # Orange
                    elif tier == QualityTier.TRACKABLE_BUT_SMALL:
                        label = f"T#{track_id}: Small Face"
                        color = (255, 255, 0) # Cyan/Yellow
                    else:
                        # RECOGNITION_SAFE
                        if obs.pad_res and not obs.pad_res.passed:
                            label = f"T#{track_id}: SPOOF ({obs.pad_res.score:.2f})"
                            color = (0, 0, 255) # Red
                        elif obs.matched_id:
                            label = f"T#{track_id}: {obs.matched_name} ({obs.similarity:.2f})"
                            color = (0, 255, 0) # Green
                        else:
                            label = f"T#{track_id}: Unknown ({obs.similarity:.2f})"
                            color = (0, 165, 255)

                    active_hud_overlays.append((box, label, color))

            # Render HUD overlays on smooth preview frame
            for box, label, color in active_hud_overlays:
                cv2.rectangle(display_frame, (box[0], box[1]), (box[2], box[3]), color, 2)
                cv2.rectangle(display_frame, (box[0], max(0, box[1] - 22)), (box[2], box[1]), color, cv2.FILLED)
                cv2.putText(display_frame, label, (box[0] + 4, max(12, box[1] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

            # Draw Window Status Bar
            header_text = f"[{window}] Slot: {slot_id} | Time Remaining: {remaining_sec}s | Active Tracks: {len(tracker.active_tracks)}"
            cv2.rectangle(display_frame, (0, 0), (FRAME_WIDTH, 28), (20, 20, 20), cv2.FILLED)
            cv2.putText(display_frame, header_text, (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255), 1)

            if show_window:
                cv2.imshow(window_name, display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    print(f"[{window}] Burst capture interrupted by user.")
                    break

    finally:
        camera.stop()
        if show_window:
            cv2.destroyAllWindows()

    # =========================================================================
    # 5. BURST-LEVEL AGGREGATION & ATOMIC ATTENDANCE COMMIT (ONCE PER WINDOW)
    # =========================================================================
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Burst duration complete. Evaluating accumulated classroom tracks...")
    all_tracks = tracker.get_all_tracks()
    print(f"[{window}] Total tracks tracked across burst: {len(all_tracks)}")

    evaluation = BurstDecisionAggregator.evaluate_burst_window(all_tracks, enrolled_student_ids)
    records = evaluation["records"]
    present_count = 0
    unresolved_count = 0

    for rec in records:
        sid = rec["student_id"]
        status = rec["status"]
        conf = rec["confidence"]
        sname = rec["student_name"] or sid

        if status == "PRESENT":
            present_count += 1
            record_window_attendance(sid, slot_id, window, conf, status="PRESENT")
            print(f"  -> [COMMITTED PRESENT]: {sname} ({sid}) | Conf: {conf:.2f} | Valid Obs: {rec['valid_obs']} | PAD: {rec['pad_score']:.2f}")
        elif status == "UNRESOLVED":
            unresolved_count += 1
            record_window_attendance(sid, slot_id, window, conf, status="UNRESOLVED")
            print(f"  -> [COMMITTED UNRESOLVED]: {sname} ({sid}) | Reason: {rec['reason']}")
        else:
            # ABSENT - Record absent state if record exists or maintain absent default
            pass

    # 6. Save deduplicated unknown face crops
    saved_unknown_embeddings = []
    unknown_count = 0
    for u_track in evaluation["unknown_tracks"]:
        if u_track.best_crop is not None and u_track.best_crop.size > 0:
            unknown_count += 1
            img_filename = f"unknown_{datetime.now().strftime('%H%M%S')}_t{u_track.track_id}.jpg"
            img_path = os.path.join(slot_unknown_dir, img_filename)
            cv2.imwrite(img_path, u_track.best_crop)
            add_unknown_face(slot_id, window, img_path)
            print(f"  -> [UNKNOWN FACE ARCHIVED]: Track #{u_track.track_id} saved to {img_path}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed {window} Burst: {present_count} Present, {unresolved_count} Unresolved, {unknown_count} Unknown Alert(s).\n")
