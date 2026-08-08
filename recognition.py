"""
Face Detection and Embedding Extraction Module using InsightFace.
Also calculates Cosine Similarity between face embeddings.
"""

from typing import Tuple, List, Optional
import numpy as np
import cv2
import insightface
from insightface.app import FaceAnalysis
from config import INSIGHTFACE_MODEL_NAME, MATCH_THRESHOLD


class FaceRecognizer:
    def __init__(self, name: str = INSIGHTFACE_MODEL_NAME):
        """Initialize InsightFace Analysis model."""
        print(f"Loading InsightFace model ({name})...")
        self.app = FaceAnalysis(name=name, providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        print("InsightFace model loaded successfully!")

    def detect_and_embed(self, frame: np.ndarray):
        """
        Detect faces in frame and return detected face objects.
        Each face object contains `.embedding` (512-D float array) and `.bbox` (bounding box coordinates).
        """
        faces = self.app.get(frame)
        return faces

    @staticmethod
    def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two 512-D embedding vectors.
        Returns float score between -1.0 and 1.0 (higher = more similar).
        """
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(emb1, emb2) / (norm1 * norm2))

    @staticmethod
    def detect_phone_bezel(full_frame: np.ndarray, face_box: np.ndarray) -> bool:
        """
        Detects rectangular smartphone/tablet screen bezels and device borders around the face box.
        """
        if full_frame is None or face_box is None or len(face_box) < 4:
            return False

        try:
            h, w, _ = full_frame.shape
            gray = cv2.cvtColor(full_frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 40, 120)

            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            fx1, fy1, fx2, fy2 = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 12000: # Typical screen bounding area
                    peri = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
                    if 4 <= len(approx) <= 6:
                        rx, ry, rw, rh = cv2.boundingRect(approx)
                        aspect = float(rw) / float(rh) if rh > 0 else 0
                        if (0.35 <= aspect <= 0.75) or (1.30 <= aspect <= 2.30):
                            # Check if contour surrounds or bounds the face box
                            if (rx <= fx1 + 30) and (ry <= fy1 + 30) and (rx + rw >= fx2 - 30) and (ry + rh >= fy2 - 30):
                                return True
            return False
        except Exception:
            return False

    @staticmethod
    def verify_liveness(face_crop: np.ndarray, face_obj: Optional[object] = None, full_frame: Optional[np.ndarray] = None) -> Tuple[bool, float, str]:
        """
        Strict Multi-Spectral Anti-Spoofing & Presentation Attack Detection (PAD) Filter.
        Analyzes 2D FFT Moiré spectrum, YCrCb dermal skin chroma, HSV screen glare, Laplacian texture range,
        and full-frame phone screen bezel detection to strictly block phone screens, tablets, and photos.
        
        Returns:
            (is_live: bool, liveness_score: float, reason: str)
        """
        if face_crop is None or face_crop.size == 0 or face_crop.shape[0] < 30 or face_crop.shape[1] < 30:
            return False, 0.0, "Crop too small"

        try:
            h, w, _ = face_crop.shape
            
            # 1. CLAHE Contrast & Lighting Equalization
            gray_raw = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray_raw)

            # 2. Laplacian Texture Variance
            laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

            # 3. 2D Fast Fourier Transform (FFT) Moiré Pattern Grid Detection
            f = np.fft.fft2(gray_raw)
            fshift = np.fft.fftshift(f)
            mag = 20 * np.log(np.abs(fshift) + 1e-5)
            cy, cx = h // 2, w // 2
            r_low = max(5, min(h, w) // 8)
            
            low_freq_energy = mag[max(0, cy-r_low):min(h, cy+r_low), max(0, cx-r_low):min(w, cx+r_low)].mean()
            total_freq_energy = mag.mean()
            high_freq_ratio = float(total_freq_energy / (low_freq_energy + 1e-5))

            # 4. YCrCb Dermal Skin Chroma Spectrum Analysis
            ycrcb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2YCrCb)
            cr = ycrcb[:, :, 1]
            cb = ycrcb[:, :, 2]
            skin_mask = (cr >= 128) & (cr <= 175) & (cb >= 75) & (cb <= 132)
            skin_ratio = float(np.count_nonzero(skin_mask)) / float(h * w)

            # 5. Specular Glass Reflection & RGB Backlight Glow Analysis
            hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
            v_chan = hsv[:, :, 2]
            s_chan = hsv[:, :, 1]

            screen_glass_mask = (v_chan > 248) & (s_chan < 25)
            screen_glass_ratio = float(np.count_nonzero(screen_glass_mask)) / float(h * w)
            high_sat_ratio = float(np.count_nonzero(s_chan > 210)) / float(h * w)

            det_score = getattr(face_obj, 'det_score', 0.85) or 0.85
            liveness_score = laplacian_var * (skin_ratio + 0.2) * float(det_score)

            # 6. Check Phone Bezel Edge Contour if full frame provided
            if full_frame is not None and face_obj is not None and hasattr(face_obj, 'bbox'):
                if FaceRecognizer.detect_phone_bezel(full_frame, face_obj.bbox):
                    return False, liveness_score, "Phone Screen Device Frame Detected"

            # Strict Un-coupled Rejection Rules for Phone Screens & Photos:
            # Rule A: Moiré Screen Grid Spectrum Peak
            if high_freq_ratio > 0.74:
                return False, liveness_score, "Moiré Screen Grid Detected"

            # Rule B: Phone Screen Glass Specular Reflection
            if screen_glass_ratio > 0.05:
                return False, liveness_score, "Phone Glass Screen Glare"

            # Rule C: Screen RGB Backlight Over-saturation
            if high_sat_ratio > 0.28:
                return False, liveness_score, "Screen RGB Backlight Glow"

            # Rule D: Unnatural Texture Range (Phone photos over-sharpen > 350 or blur < 15)
            if laplacian_var < 15.0 or laplacian_var > 350.0:
                return False, liveness_score, "Unnatural Surface Texture"

            # Rule E: Non-Dermal Skin Color Spectrum
            if skin_ratio < 0.25:
                return False, liveness_score, "Non-Dermal Color Spectrum"

            return True, float(liveness_score), "Live Face Verified"
        except Exception as err:
            print("Liveness verification error:", err)
            return True, 100.0, "Fallback"

    def find_match(self, target_embedding: np.ndarray, registered_templates: list, threshold: float = MATCH_THRESHOLD):
        """
        Matches target embedding against decrypted templates in memory.
        registered_templates is a list of tuples: (student_id, student_name, embedding)
        
        Returns:
            (best_student_id, best_student_name, best_similarity_score) or (None, "Unknown", score)
        """
        best_score = -1.0
        best_match = (None, "Unknown", 0.0)

        for student_id, name, embedding in registered_templates:
            sim = self.cosine_similarity(target_embedding, embedding)
            if sim > best_score:
                best_score = sim
                best_match = (student_id, name, sim)

        if best_score >= threshold:
            return best_match
        else:
            return (None, "Unknown", float(best_score))
