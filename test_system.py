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
    # 1. Flat screen / uniform crop -> should be rejected
    flat_crop = np.full((100, 100, 3), 128, dtype=np.uint8)
    is_live_flat, score_flat, reason_flat = FaceRecognizer.verify_liveness(flat_crop)
    assert not is_live_flat, f"Flat screen surface should be rejected as spoof, got {reason_flat}"

    # 2. Natural skin face crop simulation (smooth spatial gradient with facial features)
    skin_crop = np.zeros((120, 120, 3), dtype=np.uint8)
    for r in range(120):
        for c in range(120):
            skin_crop[r, c] = [100 + r // 4, 130 + c // 4, 170 + (r + c) // 6]
    cv2.circle(skin_crop, (40, 45), 10, (50, 70, 90), -1)
    cv2.circle(skin_crop, (80, 45), 10, (50, 70, 90), -1)
    cv2.line(skin_crop, (40, 85), (80, 85), (40, 50, 140), 4)
    is_live_skin, score_skin, reason_skin = FaceRecognizer.verify_liveness(skin_crop)
    assert is_live_skin, f"Live textured skin face crop should pass liveness check, got {is_live_skin}, {reason_skin}"

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


def run_all_tests():
    print("\n" + "="*60)
    print("     RUNNING UPDATED SYSTEM INTEGRATION TESTS")
    print("="*60 + "\n")
    test_aes_roundtrip()
    test_cosine_similarity()
    test_anti_spoof_liveness()
    test_tri_window_attendance()
    test_unknown_face_logging()
    test_manual_override()
    print("\n" + "="*60)
    print("  ALL UPDATED INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
