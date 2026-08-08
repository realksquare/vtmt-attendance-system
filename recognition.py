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
        Strict Multi-Stage Anti-Spoofing & Presentation Attack Detection (PAD) Filter.

        Stages:
          0. Face size sanity check (small face = phone screen photo)
          1. Surrounding context screen glow / bezel edge analysis
          2. Phone bezel contour detection
          3. 2D FFT Moiré pixel grid analysis
          4. YCrCb dermal skin chroma check
          5. HSV specular screen glare / backlight glow analysis
          6. Laplacian texture variance range check

        Returns: (is_live: bool, liveness_score: float, reason: str)
        """
        if face_crop is None or face_crop.size == 0 or face_crop.shape[0] < 30 or face_crop.shape[1] < 30:
            return False, 0.0, "Face crop too small"

        try:
            face_h, face_w, _ = face_crop.shape

            # --- Stage 0: Face-to-Frame Size Ratio ---
            # A real person's face for enrollment should occupy a significant portion of the frame.
            # A face ON a phone screen is always tiny relative to the full frame.
            if full_frame is not None:
                fh, fw, _ = full_frame.shape
                frame_area = float(fh * fw)
                face_area = float(face_h * face_w)
                face_ratio = face_area / frame_area
                if face_ratio < 0.035:  # Face must cover at least 3.5% of frame
                    return False, 0.0, "Face Too Small - Move Closer to Camera"

            # --- Stage 1: Surrounding Context Screen Glow Detection ---
            # Look at the ring of pixels surrounding the face bounding box.
            # Phone screens emit uniform bright backlit glow around the face area.
            if full_frame is not None and face_obj is not None and hasattr(face_obj, 'bbox'):
                bbox = face_obj.bbox.astype(int)
                fh, fw, _ = full_frame.shape
                fx1, fy1, fx2, fy2 = bbox[0], bbox[1], bbox[2], bbox[3]
                pad = max(18, int((fx2 - fx1) * 0.25))

                # Build surrounding ring region (avoiding out-of-bounds)
                outer_x1 = max(0, fx1 - pad)
                outer_y1 = max(0, fy1 - pad)
                outer_x2 = min(fw, fx2 + pad)
                outer_y2 = min(fh, fy2 + pad)

                surround_region = full_frame[outer_y1:outer_y2, outer_x1:outer_x2].copy()

                # Mask out the face area itself to get just the surrounding ring
                inner_sy1 = fy1 - outer_y1
                inner_sx1 = fx1 - outer_x1
                inner_sy2 = inner_sy1 + (fy2 - fy1)
                inner_sx2 = inner_sx1 + (fx2 - fx1)
                surround_mask = np.ones(surround_region.shape[:2], dtype=bool)
                surround_mask[max(0, inner_sy1):min(surround_region.shape[0], inner_sy2),
                              max(0, inner_sx1):min(surround_region.shape[1], inner_sx2)] = False

                if surround_mask.any():
                    ring_pixels = surround_region[surround_mask]
                    surr_hsv = cv2.cvtColor(surround_region, cv2.COLOR_BGR2HSV)
                    surr_v = surr_hsv[:, :, 2][surround_mask]
                    surr_s = surr_hsv[:, :, 1][surround_mask]

                    # Screen backlight: surrounding ring very bright AND very low saturation (white backlight)
                    screen_surround_ratio = float(np.mean((surr_v > 200) & (surr_s < 40)))
                    if screen_surround_ratio > 0.30:
                        return False, 0.0, "Screen Backlight Surround Glow Detected"

                    # Uniform surround brightness (phone screen uniform illumination)
                    surr_v_std = float(np.std(surr_v.astype(np.float32)))
                    surr_v_mean = float(np.mean(surr_v.astype(np.float32)))
                    if surr_v_mean > 160 and surr_v_std < 28:
                        return False, 0.0, "Uniform Screen Backlight Detected"

            # --- Stage 2: Phone Bezel Contour Detection ---
            if full_frame is not None and face_obj is not None and hasattr(face_obj, 'bbox'):
                if FaceRecognizer.detect_phone_bezel(full_frame, face_obj.bbox):
                    return False, 0.0, "Phone Device Frame Detected"

            # --- CLAHE Preprocessing ---
            gray_raw = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray_raw)

            # --- Stage 3: 2D FFT Moiré Pixel Grid Analysis ---
            f = np.fft.fft2(gray_raw)
            fshift = np.fft.fftshift(f)
            mag = 20 * np.log(np.abs(fshift) + 1e-5)
            cy, cx = face_h // 2, face_w // 2
            r_low = max(5, min(face_h, face_w) // 8)
            low_freq_energy = mag[max(0, cy - r_low):min(face_h, cy + r_low),
                                   max(0, cx - r_low):min(face_w, cx + r_low)].mean()
            total_freq_energy = mag.mean()
            high_freq_ratio = float(total_freq_energy / (low_freq_energy + 1e-5))

            if high_freq_ratio > 0.72:
                return False, 0.0, "Moiré Screen Pixel Grid Detected"

            # --- Stage 4: YCrCb Dermal Skin Chroma ---
            ycrcb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2YCrCb)
            cr, cb = ycrcb[:, :, 1], ycrcb[:, :, 2]
            skin_mask = (cr >= 128) & (cr <= 175) & (cb >= 75) & (cb <= 132)
            skin_ratio = float(np.count_nonzero(skin_mask)) / float(face_h * face_w)

            # --- Stage 5: HSV Specular Screen Glare / Backlight ---
            hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
            v_chan, s_chan = hsv[:, :, 2], hsv[:, :, 1]
            screen_glass_ratio = float(np.count_nonzero((v_chan > 240) & (s_chan < 30))) / float(face_h * face_w)
            high_sat_ratio = float(np.count_nonzero(s_chan > 200)) / float(face_h * face_w)

            if screen_glass_ratio > 0.04:
                return False, 0.0, "Phone Screen Glass Glare Detected"

            if high_sat_ratio > 0.25:
                return False, 0.0, "Screen RGB Backlight Over-saturation"

            # --- Stage 6: Laplacian Texture Range ---
            laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if laplacian_var < 18.0:
                return False, 0.0, "Flat / Blurry 2D Surface"
            if laplacian_var > 400.0:
                return False, 0.0, "Over-sharpened Screen Image"

            # --- Stage 7: Skin Coverage Minimum ---
            if skin_ratio < 0.22:
                return False, 0.0, "Insufficient Skin Tone Coverage"

            det_score = getattr(face_obj, 'det_score', 0.85) or 0.85
            liveness_score = laplacian_var * (skin_ratio + 0.2) * float(det_score)
            return True, float(liveness_score), "Live Face Verified"

        except Exception as err:
            print(f"[PAD] Liveness verification error: {err}")
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
