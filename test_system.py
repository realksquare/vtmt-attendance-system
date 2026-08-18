"""
Automated Integration Test Suite for Smart Attendance System.
Validates AES-256 encryption, Cosine similarity, 3-Tier Face Quality,
Classroom Multi-Face Tracking, Burst Decision Aggregator, MiniFASNet PAD,
Fail-Closed Security, Tri-Window Attendance Voting, and Staff Overrides.
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
from liveness.tracker import ClassroomFaceTracker, BurstDecisionAggregator, TrackEvidence, FaceObservation, MAX_TRACK_OBSERVATIONS


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


def test_pad_engine_fail_closed():
    print("Testing MiniFASNet ONNX PAD Engine & Fail-Closed Security...")
    engine = AntiSpoofEngine()
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_bbox = np.array([200, 100, 440, 380])

    # 1. Flat dummy surface -> PAD score should be low
    score, details = engine.predict_single(dummy_frame, dummy_bbox)
    assert score < 0.65, f"Flat surface should have low live score, got {score}"

    # 2. Simulated Model Unavailable / Missing Session -> MUST FAIL CLOSED (0.0, False)
    saved_session = engine.session
    engine.session = None
    res_unavail = engine.verify(dummy_frame, dummy_bbox)
    assert not res_unavail.passed, "Missing PAD model MUST fail closed"
    assert res_unavail.score == 0.0, f"Missing PAD model must return 0.0 score, got {res_unavail.score}"
    assert "Unavailable" in res_unavail.reason
    engine.session = saved_session  # Restore

    # 3. Multi-Frame Aggregator
    aggregator = MultiFramePADAggregator(min_samples=3, threshold=0.70)
    aggregator.add_sample(0.85)
    aggregator.add_sample(0.88)
    # Insufficient samples check (< 3)
    res_incomplete = aggregator.evaluate()
    assert not res_incomplete.passed, "Aggregator must fail when sample count < min_samples"

    # Add 3rd sample -> passes with median score
    aggregator.add_sample(0.86)
    res_complete = aggregator.evaluate()
    assert res_complete.passed, f"Aggregator should pass with 3 valid samples, got {res_complete.score}"
    assert abs(res_complete.score - 0.86) < 0.02, f"Expected median ~0.86, got {res_complete.score}"

    # Aggregator with an error sample -> MUST FAIL CLOSED
    aggregator_err = MultiFramePADAggregator(min_samples=2, threshold=0.70)
    aggregator_err.add_sample(0.90, {"status": "OK"})
    aggregator_err.add_sample(0.0, {"status": "PAD_ERROR"})
    res_err = aggregator_err.evaluate()
    assert not res_err.passed, "Temporal sequence containing PAD error MUST fail closed"

    print("[OK] MiniFASNet ONNX PAD Engine & Fail-Closed Security PASSED!")


def test_quality_tiers():
    print("Testing 3-Tier Face Quality Hierarchy & Soft Lighting Penalties...")
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

    # 2. Small Face (e.g. 25x25 px in back row) -> TRACKABLE_BUT_SMALL
    for y in range(50, 75):
        for x in range(50, 75):
            if (x + y) % 2 == 0:
                frame[y, x] = 210

    small_face = {"bbox": np.array([50, 50, 75, 75])}
    q_small = analyzer.assess_face(frame, small_face)
    assert q_small.tier == QualityTier.TRACKABLE_BUT_SMALL, f"Expected TRACKABLE_BUT_SMALL, got {q_small.tier}"

    # 3. Suboptimal lighting (dark face mean ~25) -> TRACKABLE_BUT_SMALL (Soft penalty, not hard drop)
    dark_frame = np.full((480, 640, 3), 25, dtype=np.uint8)
    for y in range(100, 300):
        for x in range(100, 300):
            if (x + y) % 3 == 0:
                dark_frame[y, x] = 30
    q_dark = analyzer.assess_face(dark_frame, large_face)
    assert q_dark.tier == QualityTier.TRACKABLE_BUT_SMALL, f"Suboptimal light should be TRACKABLE_BUT_SMALL, got {q_dark.tier}"

    # 4. Catastrophic near-black frame (mean ~5) -> UNUSABLE
    black_frame = np.full((480, 640, 3), 5, dtype=np.uint8)
    q_black = analyzer.assess_face(black_frame, large_face)
    assert q_black.tier == QualityTier.UNUSABLE, f"Severe darkness must be UNUSABLE, got {q_black.tier}"

    # 5. Multi-face in classroom mode (enforce_single_face=False) -> passes without rejection
    q_multi = analyzer.assess_frame(frame, [large_face, small_face], enforce_single_face=False)
    assert q_multi.passed, "Classroom mode should assess face without rejecting multi-face"

    print("[OK] 3-Tier Face Quality Hierarchy & Soft Lighting Penalties PASSED!")


def test_classroom_face_tracker():
    print("Testing Classroom Multi-Face Spatial Tracker & Bounded Buffer...")
    tracker = ClassroomFaceTracker(iou_threshold=0.25, max_centroid_dist=120.0)

    # Frame 1: 2 students detected
    obs1 = FaceObservation(timestamp=1.0, bbox=np.array([100, 100, 200, 200]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, quality_score=10.0))
    obs2 = FaceObservation(timestamp=1.0, bbox=np.array([400, 100, 500, 200]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, quality_score=10.0))
    matches1 = tracker.update([obs1, obs2])
    assert len(matches1) == 2
    id1, id2 = matches1[0][0], matches1[1][0]
    assert id1 != id2, "Initial tracks should have distinct IDs"

    # Frame 2: Slight movement (10px) -> Same track IDs must persist
    obs1_next = FaceObservation(timestamp=1.5, bbox=np.array([105, 102, 205, 202]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, quality_score=10.0))
    obs2_next = FaceObservation(timestamp=1.5, bbox=np.array([402, 98, 502, 198]), quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, quality_score=10.0))
    matches2 = tracker.update([obs1_next, obs2_next])
    assert len(matches2) == 2
    matched_map = {obs.bbox[0]: tid for tid, obs in matches2}
    assert matched_map[105] == id1, f"Track at x=105 should persist ID {id1}, got {matched_map[105]}"
    assert matched_map[402] == id2, f"Track at x=402 should persist ID {id2}, got {matched_map[402]}"

    # Test Bounded Buffer: Add 35 observations to track
    track1 = tracker.active_tracks[id1]
    for k in range(35):
        track1.add_observation(FaceObservation(
            timestamp=2.0 + k * 0.1, bbox=np.array([105, 102, 205, 202]),
            quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, quality_score=float(k))
        ))
    assert len(track1.observations) <= MAX_TRACK_OBSERVATIONS, f"Observations must be bounded <= {MAX_TRACK_OBSERVATIONS}, got {len(track1.observations)}"

    print("[OK] Classroom Multi-Face Spatial Tracker & Bounded Buffer PASSED!")


def test_small_to_safe_transition_and_voting():
    print("Testing Small-to-Safe Track Transition & Burst Aggregator Voting...")

    # Case 1: Track starts small (2 frames TRACKABLE_BUT_SMALL) and later collects 2 RECOGNITION_SAFE frames -> PRESENT
    t1 = TrackEvidence(track_id=1, first_seen=0.0, last_seen=2.0, last_bbox=np.array([100, 100, 200, 200]))
    # 2 small frames
    t1.add_observation(FaceObservation(
        timestamp=0.0, bbox=np.array([100, 100, 130, 130]),
        quality_res=QualityResult(passed=True, reason="small", tier=QualityTier.TRACKABLE_BUT_SMALL, blur_score=15.0),
        pad_res=PADResult(passed=True, score=0.85, reason="OK")
    ))
    t1.add_observation(FaceObservation(
        timestamp=0.5, bbox=np.array([100, 100, 135, 135]),
        quality_res=QualityResult(passed=True, reason="small", tier=QualityTier.TRACKABLE_BUT_SMALL, blur_score=16.0),
        pad_res=PADResult(passed=True, score=0.88, reason="OK")
    ))
    # 2 safe frames with biometric embeddings
    t1.add_observation(FaceObservation(
        timestamp=1.0, bbox=np.array([100, 100, 200, 200]),
        quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, blur_score=45.0),
        pad_res=PADResult(passed=True, score=0.92, reason="OK"),
        embedding=np.random.randn(512), matched_id="STU01", matched_name="Alice", similarity=0.82
    ))
    t1.add_observation(FaceObservation(
        timestamp=1.5, bbox=np.array([100, 100, 200, 200]),
        quality_res=QualityResult(passed=True, reason="OK", tier=QualityTier.RECOGNITION_SAFE, blur_score=48.0),
        pad_res=PADResult(passed=True, score=0.90, reason="OK"),
        embedding=np.random.randn(512), matched_id="STU01", matched_name="Alice", similarity=0.84
    ))
    dec1 = BurstDecisionAggregator.aggregate_track(t1, min_valid_obs=2)
    assert dec1.status == "PRESENT", f"Small-to-safe transition should yield PRESENT, got {dec1.status}"
    assert dec1.identity == "STU01"
    assert dec1.valid_observations_count == 2

    # Case 2: Track with only TRACKABLE_BUT_SMALL throughout burst -> UNRESOLVED
    t2 = TrackEvidence(track_id=2, first_seen=0.0, last_seen=2.0, last_bbox=np.array([50, 50, 75, 75]))
    for i in range(4):
        t2.add_observation(FaceObservation(
            timestamp=i * 0.5, bbox=np.array([50, 50, 75, 75]),
            quality_res=QualityResult(passed=True, reason="small", tier=QualityTier.TRACKABLE_BUT_SMALL, blur_score=15.0),
            pad_res=PADResult(passed=True, score=0.80, reason="OK")
        ))
    dec2 = BurstDecisionAggregator.aggregate_track(t2, min_valid_obs=2)
    assert dec2.status == "UNRESOLVED", f"Small throughout must produce UNRESOLVED, got {dec2.status}"

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

    # Case 4: Multi-Frame PAD Spoof failure -> UNRESOLVED (fails closed)
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

    print("[OK] Small-to-Safe Track Transition & Burst Aggregator Voting PASSED!")


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
    print("     RUNNING AUDITED SYSTEM INTEGRATION TESTS")
    print("="*60 + "\n")
    test_aes_roundtrip()
    test_cosine_similarity()
    test_anti_spoof_liveness()
    test_pad_engine_fail_closed()
    test_quality_tiers()
    test_classroom_face_tracker()
    test_small_to_safe_transition_and_voting()
    test_tri_window_attendance()
    test_unknown_face_logging()
    test_manual_override()
    print("\n" + "="*60)
    print("  ALL AUDITED INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
