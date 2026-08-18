"""
Automated Integration Test Suite for Smart Attendance System.
Validates AES-256 encryption, Cosine similarity, 3-Tier Face Quality,
Classroom Multi-Face Tracking, Burst Decision Aggregator, MiniFASNet PAD,
Tri-Window Attendance Voting, and Staff Overrides.
"""

import os
import cv2
import numpy as np
from config import SECRET_KEY_PATH, DB_PATH, UNKNOWNS_DIR, MATCH_THRESHOLD, PAD_SCORE_THRESHOLD
from encrypt import get_or_create_key, encrypt_embedding, decrypt_embedding
from database import (
    init_db, add_student_with_embedding, get_all_decrypted_templates,
    record_window_attendance, add_unknown_face, manual_override_attendance,
    SessionLocal, Student, HourlyAttendance, UnknownFace, get_all_timetable_slots
)
from recognition import FaceRecognizer
from liveness.quality import FaceQualityAnalyzer, QualityTier, QualityResult
from liveness.pad_engine import AntiSpoofEngine, MultiFramePADAggregator, PADResult
from liveness.challenge import LivenessChallengeController, ChallengeAction, ChallengeState
from liveness.verification import DecisionEngine, ReasonCode
from liveness.tracker import ClassroomFaceTracker, BurstDecisionAggregator, TrackEvidence, FaceObservation


def test_aes_roundtrip():
    print("Testing AES-256 GCM encryption/decryption roundtrip...")
    key = get_or_create_key()
    assert len(key) == 32, "Key length must be 32 bytes (256 bits)"

    original = np.random.randn(512).astype(np.float32)
    original /= np.linalg.norm(original)

    ciphertext, nonce, tag = encrypt_embedding(original, key)
    decrypted = decrypt_embedding(ciphertext, nonce, tag, key)

    np.testing.assert_allclose(original, decrypted, rtol=1e-5, atol=1e-5)
    print("[OK] AES-256 GCM roundtrip PASSED!")


def test_cosine_similarity():
    print("Testing Cosine Similarity calculation...")
    v1 = np.random.randn(512).astype(np.float32)
    v1 /= np.linalg.norm(v1)

    sim_self = FaceRecognizer.cosine_similarity(v1, v1)
    assert abs(sim_self - 1.0) < 1e-4, f"Self-similarity should be ~1.0, got {sim_self}"

    sim_opp = FaceRecognizer.cosine_similarity(v1, -v1)
    assert abs(sim_opp - (-1.0)) < 1e-4, f"Opposite similarity should be ~-1.0, got {sim_opp}"

    print("[OK] Cosine Similarity PASSED!")


def test_anti_spoof_liveness():
    print("Testing Anti-Spoofing & Presentation Attack Detection (PAD)...")
    # 1. Flat uniform screen-like surface -> should be rejected
    flat_crop = np.full((100, 100, 3), 128, dtype=np.uint8)
    is_live_flat, _, reason_flat = FaceRecognizer.verify_liveness(flat_crop)
    assert not is_live_flat, f"Flat screen surface should be rejected, got: {reason_flat}"

    # 2. Live realistic skin-tone face crop
    skin_crop = np.zeros((140, 140, 3), dtype=np.uint8)
    for r in range(140):
        for c in range(140):
            skin_crop[r, c] = [
                int(100 + 15 * np.sin(r * 0.15) + 5 * np.cos(c * 0.2)),
                int(145 + 10 * np.cos(r * 0.12) + 8 * np.sin(c * 0.15)),
                int(190 + 12 * np.sin((r + c) * 0.08))
            ]
    cv2.circle(skin_crop, (45, 50), 12, (70, 90, 110), -1)
    cv2.circle(skin_crop, (95, 50), 12, (70, 90, 110), -1)
    cv2.ellipse(skin_crop, (70, 100), (25, 12), 0, 0, 180, (80, 80, 160), 3)
    cv2.line(skin_crop, (70, 60), (70, 85), (130, 140, 175), 2)
    noise = np.random.randint(-8, 8, skin_crop.shape, dtype=np.int16)
    skin_crop = np.clip(skin_crop.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    skin_crop = cv2.GaussianBlur(skin_crop, (3, 3), 0)

    is_live_skin, score_skin, reason_skin = FaceRecognizer.verify_liveness(skin_crop)
    assert is_live_skin, f"Realistic skin face crop should pass liveness check, got: is_live={is_live_skin}, reason={reason_skin}"
    print("[OK] Anti-Spoofing Presentation Attack Detection PASSED!")


def test_quality_tiers():
    print("Testing 3-Tier Face Quality Hierarchy...")
    analyzer = FaceQualityAnalyzer()
    frame = np.full((480, 640, 3), 130, dtype=np.uint8)
    # Add high-frequency texture inside face area
    for y in range(100, 300):
        for x in range(100, 300):
            if (x + y) % 3 == 0:
                frame[y, x] = 200

    # 1. Clear Large Face -> RECOGNITION_SAFE
    large_face = {"bbox": np.array([100, 100, 300, 300])}
    q_safe = analyzer.assess_face(frame, large_face)
    assert q_safe.tier == QualityTier.RECOGNITION_SAFE, f"Expected RECOGNITION_SAFE, got {q_safe.tier}"

    # Add texture inside small face region [50:75, 50:75]
    for y in range(50, 75):
        for x in range(50, 75):
            if (x + y) % 2 == 0:
                frame[y, x] = 210

    # 2. Small Face (e.g. 25x25 px in back row) -> TRACKABLE_BUT_SMALL
    small_face = {"bbox": np.array([50, 50, 75, 75])}
    q_small = analyzer.assess_face(frame, small_face)
    assert q_small.tier == QualityTier.TRACKABLE_BUT_SMALL, f"Expected TRACKABLE_BUT_SMALL, got {q_small.tier}"

    # 3. Blurry / Flat Face -> UNUSABLE
    flat_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    blurry_face = {"bbox": np.array([100, 100, 300, 300])}
    q_unusable = analyzer.assess_face(flat_frame, blurry_face)
    assert q_unusable.tier == QualityTier.UNUSABLE, f"Expected UNUSABLE for flat image, got {q_unusable.tier}"

    # 4. Multi-face in classroom mode (enforce_single_face=False) -> passes without rejection
    q_multi = analyzer.assess_frame(frame, [large_face, small_face], enforce_single_face=False)
    assert q_multi.passed, "Classroom mode should assess face without rejecting multi-face"

    print("[OK] 3-Tier Face Quality Hierarchy PASSED!")


def test_classroom_face_tracker():
    print("Testing Classroom Multi-Face Spatial Tracker...")
    tracker = ClassroomFaceTracker(iou_threshold=0.25, max_centroid_dist=120.0)

    # Frame 1: 2 students detected
    obs1 = FaceObservation(timestamp=1.0, bbox=np.array([100, 100, 200, 200]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE))
    obs2 = FaceObservation(timestamp=1.0, bbox=np.array([400, 100, 500, 200]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE))
    matches1 = tracker.update([obs1, obs2])
    assert len(matches1) == 2
    id1, id2 = matches1[0][0], matches1[1][0]
    assert id1 != id2, "Initial tracks should have distinct IDs"

    # Frame 2: Slight movement (10px) -> Same track IDs must persist
    obs1_next = FaceObservation(timestamp=1.5, bbox=np.array([105, 102, 205, 202]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE))
    obs2_next = FaceObservation(timestamp=1.5, bbox=np.array([402, 98, 502, 198]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE))
    matches2 = tracker.update([obs1_next, obs2_next])
    assert len(matches2) == 2
    matched_map = {obs.bbox[0]: tid for tid, obs in matches2}
    assert matched_map[105] == id1, f"Track at x=105 should persist ID {id1}, got {matched_map[105]}"
    assert matched_map[402] == id2, f"Track at x=402 should persist ID {id2}, got {matched_map[402]}"

    all_tracks = tracker.get_all_tracks()
    assert len(all_tracks) == 2
    assert len(all_tracks[0].observations) == 2
    print("[OK] Classroom Multi-Face Spatial Tracker PASSED!")


def test_burst_decision_aggregator():
    print("Testing Burst Decision Aggregator & Candidate Voting...")

    # Case 1: Single Frame cannot mark attendance alone (< 2 valid observations) -> UNRESOLVED
    t1 = TrackEvidence(track_id=1, first_seen=0.0, last_seen=0.5, last_bbox=np.array([100, 100, 200, 200]))
    t1.add_observation(FaceObservation(
        timestamp=0.0, bbox=np.array([100, 100, 200, 200]),
        quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, blur_score=40.0),
        pad_res=PADResult(passed=True, score=0.92, reason="OK"),
        embedding=np.random.randn(512), matched_id="STU01", matched_name="Alice", similarity=0.85
    ))
    dec1 = BurstDecisionAggregator.aggregate_track(t1, min_valid_obs=2)
    assert dec1.status == "UNRESOLVED", f"Single frame must be UNRESOLVED, got {dec1.status}"

    # Case 2: Multi-frame consistent observations (4 frames) with 1 bad blurry frame -> PRESENT
    t2 = TrackEvidence(track_id=2, first_seen=0.0, last_seen=2.0, last_bbox=np.array([100, 100, 200, 200]))
    # Add 3 good frames
    for i in range(3):
        t2.add_observation(FaceObservation(
            timestamp=i * 0.5, bbox=np.array([100, 100, 200, 200]),
            quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, blur_score=45.0),
            pad_res=PADResult(passed=True, score=0.88 + i*0.02, reason="OK"),
            embedding=np.random.randn(512), matched_id="STU01", matched_name="Alice", similarity=0.82
        ))
    # Add 1 blurry frame (should be ignored for recognition without ruining burst)
    t2.add_observation(FaceObservation(
        timestamp=1.8, bbox=np.array([100, 100, 200, 200]),
        quality_res=QualityResult(passed=False, reason="Motion blur", tier=QualityTier.UNUSABLE, blur_score=5.0)
    ))
    dec2 = BurstDecisionAggregator.aggregate_track(t2, min_valid_obs=2)
    assert dec2.status == "PRESENT", f"Expected PRESENT, got {dec2.status}"
    assert dec2.identity == "STU01"
    assert dec2.valid_observations_count == 3

    # Case 3: Conflicting Identity votes (50% STU01, 50% STU02) -> UNRESOLVED
    t3 = TrackEvidence(track_id=3, first_seen=0.0, last_seen=2.0, last_bbox=np.array([100, 100, 200, 200]))
    t3.add_observation(FaceObservation(
        timestamp=0.0, bbox=np.array([100, 100, 200, 200]),
        quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, blur_score=40.0),
        pad_res=PADResult(passed=True, score=0.90, reason="OK"),
        embedding=np.random.randn(512), matched_id="STU01", matched_name="Alice", similarity=0.75
    ))
    t3.add_observation(FaceObservation(
        timestamp=0.5, bbox=np.array([100, 100, 200, 200]),
        quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, blur_score=40.0),
        pad_res=PADResult(passed=True, score=0.90, reason="OK"),
        embedding=np.random.randn(512), matched_id="STU02", matched_name="Bob", similarity=0.76
    ))
    dec3 = BurstDecisionAggregator.aggregate_track(t3, min_valid_obs=1, support_ratio_thresh=0.60)
    assert dec3.status == "UNRESOLVED", f"Conflicting identities must produce UNRESOLVED, got {dec3.status}"

    # Case 4: PAD Spoof failure across track -> UNRESOLVED (fails closed)
    t4 = TrackEvidence(track_id=4, first_seen=0.0, last_seen=1.5, last_bbox=np.array([100, 100, 200, 200]))
    for i in range(3):
        t4.add_observation(FaceObservation(
            timestamp=i * 0.5, bbox=np.array([100, 100, 200, 200]),
            quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, blur_score=40.0),
            pad_res=PADResult(passed=False, score=0.25, reason="Phone screen attack"),
            embedding=np.random.randn(512), matched_id="STU01", matched_name="Alice", similarity=0.95
        ))
    dec4 = BurstDecisionAggregator.aggregate_track(t4, min_valid_obs=2)
    assert dec4.status == "UNRESOLVED", f"PAD failure must fail closed, got {dec4.status}"
    assert not dec4.pad_passed

    print("[OK] Burst Decision Aggregator & Candidate Voting PASSED!")


def test_tri_window_attendance():
    print("Testing Tri-Window 2-out-of-3 Attendance Logic with UNRESOLVED support...")
    init_db()
    key = get_or_create_key()
    slots = get_all_timetable_slots()
    test_slot = slots[0].slot_id

    import time
    test_id = f"TEST_STUDENT_{int(time.time())}"
    dummy_embedding = np.random.randn(512).astype(np.float32)
    dummy_embedding /= np.linalg.norm(dummy_embedding)

    add_student_with_embedding(test_id, "Test Burst Student", "CS", "FYP", dummy_embedding, key)

    # 1. Mark Window A -> status should be PARTIAL (1 window PRESENT)
    record_window_attendance(test_id, test_slot, "WINDOW_A", confidence=0.88, status="PRESENT")
    
    db = SessionLocal()
    rec = db.query(HourlyAttendance).filter(HourlyAttendance.student_id == test_id, HourlyAttendance.slot_id == test_slot).first()
    assert rec is not None, "Hourly attendance record should exist"
    assert rec.window_a_status == "PRESENT", "Window A status should be PRESENT"
    assert rec.final_status == "PARTIAL", f"Expected PARTIAL for 1 window, got {rec.final_status}"
    db.close()

    # 2. Mark Window B as UNRESOLVED -> final status remains PARTIAL
    record_window_attendance(test_id, test_slot, "WINDOW_B", confidence=0.60, status="UNRESOLVED")
    db = SessionLocal()
    rec = db.query(HourlyAttendance).filter(HourlyAttendance.student_id == test_id, HourlyAttendance.slot_id == test_slot).first()
    assert rec.window_b_status == "UNRESOLVED", "Window B status should be UNRESOLVED"
    assert rec.final_status == "PARTIAL", f"Expected PARTIAL, got {rec.final_status}"
    db.close()

    # 3. Mark Window C -> status upgrades to PRESENT (2 out of 3 windows PRESENT!)
    record_window_attendance(test_id, test_slot, "WINDOW_C", confidence=0.91, status="PRESENT")
    db = SessionLocal()
    rec = db.query(HourlyAttendance).filter(HourlyAttendance.student_id == test_id, HourlyAttendance.slot_id == test_slot).first()
    assert rec.window_c_status == "PRESENT", "Window C status should be PRESENT"
    assert rec.final_status == "PRESENT", f"Expected PRESENT for 2 out of 3 windows, got {rec.final_status}"
    db.close()

    print("[OK] Tri-Window 2-out-of-3 Attendance Logic PASSED!")


def test_unknown_face_logging():
    print("Testing Unknown Face Image Archiving...")
    init_db()
    test_img_path = os.path.join(UNKNOWNS_DIR, "test_unknown.jpg")
    with open(test_img_path, "wb") as f:
        f.write(b"dummy image bytes")

    add_unknown_face("SLOT_0900_1000", "WINDOW_A", test_img_path)

    db = SessionLocal()
    uf = db.query(UnknownFace).filter(UnknownFace.image_path == test_img_path).first()
    assert uf is not None, "Unknown face record should be stored in database"
    assert uf.window == "WINDOW_A", "Window should match"
    db.close()
    print("[OK] Unknown Face Archiving PASSED!")


def test_manual_override():
    print("Testing Staff Manual Attendance Override...")
    init_db()
    test_id = "TEST_STUDENT_BURST_01"
    slots = get_all_timetable_slots()
    test_slot = slots[0].slot_id

    success = manual_override_attendance(test_id, test_slot, "EXCUSED", "Medical Certificate Provided")
    assert success, "Manual override failed"

    db = SessionLocal()
    rec = db.query(HourlyAttendance).filter(HourlyAttendance.student_id == test_id, HourlyAttendance.slot_id == test_slot).first()
    assert rec.final_status == "EXCUSED", f"Expected EXCUSED, got {rec.final_status}"
    assert "Medical" in rec.remarks, "Remarks should contain medical note"
    db.close()
    print("[OK] Staff Manual Override PASSED!")


def run_all_tests():
    print("\n" + "="*60)
    print("     RUNNING UPDATED SYSTEM INTEGRATION TESTS")
    print("="*60 + "\n")
    test_aes_roundtrip()
    test_cosine_similarity()
    test_anti_spoof_liveness()
    test_quality_tiers()
    test_classroom_face_tracker()
    test_burst_decision_aggregator()
    test_tri_window_attendance()
    test_unknown_face_logging()
    test_manual_override()
    print("\n" + "="*60)
    print("  ALL UPDATED INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
