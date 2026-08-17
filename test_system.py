"""
Automated Integration Test Suite for Smart Attendance System.
Validates AES-256 encryption, Cosine similarity, Dual-Window Hourly Attendance,
Unknown Face archiving, and Staff Manual Overrides.
"""

import os
import cv2
import numpy as np
from config import SECRET_KEY_PATH, DB_PATH, UNKNOWNS_DIR
from encrypt import get_or_create_key, encrypt_embedding, decrypt_embedding
from database import (
    init_db, add_student_with_embedding, get_all_decrypted_templates,
    record_window_attendance, add_unknown_face, manual_override_attendance,
    SessionLocal, Student, HourlyAttendance, UnknownFace, get_all_timetable_slots
)
from recognition import FaceRecognizer


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

    # 2. Live realistic skin-tone face crop (BGR skin values, natural gradient, facial structure)
    # Use actual human skin-tone BGR range that maps to YCrCb skin chroma range
    skin_crop = np.zeros((140, 140, 3), dtype=np.uint8)
    for r in range(140):
        for c in range(140):
            # Warm human skin tone: B~110, G~150, R~190 with organic variation
            skin_crop[r, c] = [
                int(100 + 15 * np.sin(r * 0.15) + 5 * np.cos(c * 0.2)),
                int(145 + 10 * np.cos(r * 0.12) + 8 * np.sin(c * 0.15)),
                int(190 + 12 * np.sin((r + c) * 0.08))
            ]
    # Add facial feature shapes (eyes, mouth) for texture
    cv2.circle(skin_crop, (45, 50), 12, (70, 90, 110), -1)   # left eye
    cv2.circle(skin_crop, (95, 50), 12, (70, 90, 110), -1)   # right eye
    cv2.ellipse(skin_crop, (70, 100), (25, 12), 0, 0, 180, (80, 80, 160), 3)  # mouth
    cv2.line(skin_crop, (70, 60), (70, 85), (130, 140, 175), 2)  # nose bridge
    # Gentle natural skin texture noise
    noise = np.random.randint(-8, 8, skin_crop.shape, dtype=np.int16)
    skin_crop = np.clip(skin_crop.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    skin_crop = cv2.GaussianBlur(skin_crop, (3, 3), 0)

    is_live_skin, score_skin, reason_skin = FaceRecognizer.verify_liveness(skin_crop)
    assert is_live_skin, f"Realistic skin face crop should pass liveness check, got: is_live={is_live_skin}, reason={reason_skin}"

    print("[OK] Anti-Spoofing Presentation Attack Detection PASSED!")


def test_tri_window_attendance():
    print("Testing Tri-Window (First 5m / Mid 5m / Last 5m) 2-out-of-3 Attendance Logic...")
    init_db()
    key = get_or_create_key()
    slots = get_all_timetable_slots()
    test_slot = slots[0].slot_id

    import time
    test_id = f"TEST_STUDENT_{int(time.time())}"
    dummy_embedding = np.random.randn(512).astype(np.float32)
    dummy_embedding /= np.linalg.norm(dummy_embedding)

    add_student_with_embedding(test_id, "Test Burst Student", "CS", "FYP", dummy_embedding, key)

    # 1. Mark Window A (First 5 mins) -> status should be PARTIAL (1 window)
    record_window_attendance(test_id, test_slot, "WINDOW_A", confidence=0.88)
    
    db = SessionLocal()
    rec = db.query(HourlyAttendance).filter(HourlyAttendance.student_id == test_id, HourlyAttendance.slot_id == test_slot).first()
    assert rec is not None, "Hourly attendance record should exist"
    assert rec.window_a_status == "PRESENT", "Window A status should be PRESENT"
    assert rec.window_b_status == "ABSENT", "Window B status should be ABSENT"
    assert rec.window_c_status == "ABSENT", "Window C status should be ABSENT"
    assert rec.final_status == "PARTIAL", f"Expected PARTIAL for 1 window, got {rec.final_status}"
    db.close()

    # 2. Mark Window C (Last 5 mins) -> status should upgrade to PRESENT (2 out of 3 windows!)
    record_window_attendance(test_id, test_slot, "WINDOW_C", confidence=0.91)
    
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


def test_pad_engine_and_aggregator():
    print("Testing MiniFASNet ONNX PAD Engine & Multi-Frame Aggregator...")
    from liveness.pad_engine import AntiSpoofEngine, MultiFramePADAggregator

    engine = AntiSpoofEngine()
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_bbox = np.array([200, 100, 440, 380])

    # 1. Flat dummy surface -> PAD score should be low
    score, details = engine.predict_single(dummy_frame, dummy_bbox)
    assert score < 0.65, f"Flat surface should have low live score, got {score}"

    # 2. Multi-Frame Aggregator
    aggregator = MultiFramePADAggregator(min_samples=5, threshold=0.65)
    for _ in range(4):
        aggregator.add_sample(0.85)
    # Insufficient samples check
    res_incomplete = aggregator.evaluate()
    assert not res_incomplete.passed, "Aggregator must fail when sample count < min_samples"

    # Add 5th sample (all high) -> should pass
    aggregator.add_sample(0.88)
    res_complete = aggregator.evaluate()
    assert res_complete.passed, f"Aggregator should pass with 5 valid samples, got {res_complete.score}"
    assert abs(res_complete.score - 0.85) < 0.05, f"Expected median ~0.85, got {res_complete.score}"

    print("[OK] MiniFASNet PAD Engine & Multi-Frame Aggregator PASSED!")


def test_quality_analyzer():
    print("Testing Face Quality Analyzer...")
    from liveness.quality import FaceQualityAnalyzer

    analyzer = FaceQualityAnalyzer()
    dummy_frame = np.full((480, 640, 3), 120, dtype=np.uint8)

    # 1. No face
    res_noface = analyzer.assess_frame(dummy_frame, [])
    assert not res_noface.passed and "No face" in res_noface.reason, f"Expected no face, got {res_noface.reason}"

    # 2. Multiple faces
    res_multiface = analyzer.assess_frame(dummy_frame, [{"bbox": [10, 10, 50, 50]}, {"bbox": [60, 60, 100, 100]}])
    assert not res_multiface.passed and "Multiple faces" in res_multiface.reason, f"Expected multiple faces, got {res_multiface.reason}"

    # 3. Face too small
    res_small = analyzer.assess_frame(dummy_frame, [{"bbox": [50, 50, 65, 65]}])
    assert not res_small.passed and "too small" in res_small.reason, f"Expected small face, got {res_small.reason}"

    # 4. Blur / Flat face crop (Laplacian variance near 0)
    flat_frame = np.full((480, 640, 3), 128, dtype=np.uint8)
    res_blur = analyzer.assess_frame(flat_frame, [{"bbox": [150, 100, 350, 300]}])
    assert not res_blur.passed and "blurry" in res_blur.reason.lower(), f"Expected blur rejection, got {res_blur.reason}"

    print("[OK] Face Quality Analyzer PASSED!")


def test_challenge_controller():
    print("Testing Active Liveness Challenge Controller...")
    from liveness.challenge import LivenessChallengeController, ChallengeAction, ChallengeState

    controller = LivenessChallengeController(action_count=2, per_action_timeout=2.0, total_timeout=5.0)
    actions = controller.start_session(explicit_actions=[ChallengeAction.TURN_LEFT, ChallengeAction.BLINK])
    assert len(actions) == 2, "Session should initialize with 2 actions"
    assert controller.state == ChallengeState.WAITING_FOR_ACTION

    # 1. Process neutral baseline
    dummy_face = {"pose": np.array([0.0, 0.0, 0.0]), "landmark_2d_106": np.zeros((106, 2))}
    state, prompt = controller.process_frame(dummy_face)
    assert state == ChallengeState.WAITING_FOR_ACTION

    # 2. Simulate Turn Left (relative yaw > 12.0 for 2 frames)
    turn_left_face = {"pose": np.array([0.0, 16.0, 0.0]), "landmark_2d_106": np.zeros((106, 2))}
    controller.process_frame(turn_left_face)
    state, _ = controller.process_frame(turn_left_face)

    # First action completed! Next action is BLINK
    assert controller.get_current_action() == ChallengeAction.BLINK

    # 3. Simulate Blink sequence (WAIT_OPEN -> OPEN_READY -> CLOSED -> REOPENED)
    # EAR > 0.23 (Open)
    open_landmarks = np.zeros((106, 2))
    open_landmarks[35] = [0, 0]; open_landmarks[39] = [20, 0]; open_landmarks[43] = [10, 6]; open_landmarks[47] = [10, 0]
    open_landmarks[89] = [0, 0]; open_landmarks[93] = [20, 0]; open_landmarks[101] = [10, 6]; open_landmarks[105] = [10, 0]
    blink_open_face = {"pose": np.array([0.0, 0.0, 0.0]), "landmark_2d_106": open_landmarks}
    controller.process_frame(blink_open_face)

    # EAR < 0.19 (Closed)
    closed_landmarks = np.zeros((106, 2))
    closed_landmarks[35] = [0, 0]; closed_landmarks[39] = [20, 0]; closed_landmarks[43] = [10, 2]; closed_landmarks[47] = [10, 0]
    closed_landmarks[89] = [0, 0]; closed_landmarks[93] = [20, 0]; closed_landmarks[101] = [10, 2]; closed_landmarks[105] = [10, 0]
    blink_closed_face = {"pose": np.array([0.0, 0.0, 0.0]), "landmark_2d_106": closed_landmarks}
    controller.process_frame(blink_closed_face)

    # EAR > 0.23 (Reopened for 2 frames)
    controller.process_frame(blink_open_face)
    final_state, _ = controller.process_frame(blink_open_face)

    assert final_state == ChallengeState.COMPLETED, f"Expected COMPLETED, got {final_state}"
    print("[OK] Active Liveness Challenge Controller PASSED!")


def test_decision_engine_fail_closed():
    print("Testing Fail-Closed Security Decision Gate...")
    from liveness.verification import DecisionEngine, ReasonCode
    from liveness.quality import QualityResult
    from liveness.pad_engine import PADResult
    from liveness.challenge import ChallengeState

    # Gate 1: All pass -> Authorized
    q_pass = QualityResult(passed=True, reason="OK")
    pad_pass = PADResult(passed=True, score=0.92, reason="OK")
    rec_pass = ("STU101", "Alice", 0.88)
    res = DecisionEngine.evaluate(q_pass, pad_pass, rec_pass, require_challenge=False)
    assert res.authorized, "All gates pass -> Must authorize"
    assert res.reason_code == ReasonCode.SUCCESS

    # Gate 2: High recognition similarity (0.99) with PAD failure -> MUST FAIL CLOSED
    pad_fail = PADResult(passed=False, score=0.20, reason="Phone photo spoof detected")
    rec_high = ("STU101", "Alice", 0.99)
    res_spoof = DecisionEngine.evaluate(q_pass, pad_fail, rec_high, require_challenge=False)
    assert not res_spoof.authorized, "PAD failure with 0.99 similarity MUST be rejected"
    assert res_spoof.reason_code == ReasonCode.PAD_SPOOF

    # Gate 3: Quality failure -> MUST FAIL CLOSED
    q_fail = QualityResult(passed=False, reason="Multiple faces detected")
    res_qual = DecisionEngine.evaluate(q_fail, pad_pass, rec_pass, require_challenge=False)
    assert not res_qual.authorized, "Quality failure MUST be rejected"
    assert res_qual.reason_code == ReasonCode.MULTIPLE_FACES

    # Gate 4: Challenge required but not completed -> MUST FAIL CLOSED
    res_chal = DecisionEngine.evaluate(q_pass, pad_pass, rec_pass, challenge_state=ChallengeState.WAITING_FOR_ACTION, require_challenge=True)
    assert not res_chal.authorized, "Incomplete challenge MUST be rejected"
    assert res_chal.reason_code == ReasonCode.CHALLENGE_FAILED

    print("[OK] Fail-Closed Security Decision Gate PASSED!")


def run_all_tests():
    print("\n" + "="*60)
    print("     RUNNING UPDATED SYSTEM INTEGRATION TESTS")
    print("="*60 + "\n")
    test_aes_roundtrip()
    test_cosine_similarity()
    test_anti_spoof_liveness()
    test_pad_engine_and_aggregator()
    test_quality_analyzer()
    test_challenge_controller()
    test_decision_engine_fail_closed()
    test_tri_window_attendance()
    test_unknown_face_logging()
    test_manual_override()
    print("\n" + "="*60)
    print("  ALL UPDATED INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()

