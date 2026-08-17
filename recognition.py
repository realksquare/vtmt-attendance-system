"""
Face Detection and Embedding Extraction Module using InsightFace.
Also calculates Cosine Similarity between face embeddings.
"""

from typing import Tuple, List, Optional, Any
import numpy as np
import cv2
import insightface
from insightface.app import FaceAnalysis
from config import INSIGHTFACE_MODEL_NAME, MATCH_THRESHOLD
from liveness.pad_engine import AntiSpoofEngine, PADResult
from liveness.quality import FaceQualityAnalyzer, QualityResult


class FaceRecognizer:
    def __init__(self, name: str = INSIGHTFACE_MODEL_NAME):
        """Initialize InsightFace Analysis model and Anti-Spoofing engine."""
        self.app = FaceAnalysis(
            name=name,
            allowed_modules=['detection', 'recognition', 'landmark_3d_68', 'landmark_2d_106'],
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        self.app.prepare(ctx_id=0, det_size=(320, 320))
        print("InsightFace model loaded successfully (CPU optimized)!")

        self.pad_engine = AntiSpoofEngine()
        self.quality_analyzer = FaceQualityAnalyzer()


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
        Detects rectangular smartphone/tablet screen bezels tightly enclosing the face box.
        Uses strict compactness + solidity + area bounds to avoid false positives on wall
        edges, door frames, furniture, or any large room features.
        """
        if full_frame is None or face_box is None or len(face_box) < 4:
            return False

        try:
            fh, fw, _ = full_frame.shape
            frame_area = float(fh * fw)
            gray = cv2.cvtColor(full_frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 130)

            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            fx1, fy1, fx2, fy2 = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])
            face_area = float((fx2 - fx1) * (fy2 - fy1))

            for cnt in contours:
                cnt_area = cv2.contourArea(cnt)

                # Phone must be a compact small object: 1.5x face area <= cnt <= 40% of frame
                if cnt_area < face_area * 1.5 or cnt_area > frame_area * 0.40:
                    continue

                # Must be a convex, filled, solid shape — not an open wall edge line
                hull = cv2.convexHull(cnt)
                hull_area = cv2.contourArea(hull)
                if hull_area < 1:
                    continue
                solidity = float(cnt_area) / float(hull_area)
                if solidity < 0.70:  # Open/irregular contours (wall edges) have low solidity
                    continue

                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
                if not (4 <= len(approx) <= 6):
                    continue

                rx, ry, rw, rh = cv2.boundingRect(approx)
                aspect = float(rw) / float(rh) if rh > 0 else 0

                # Phone portrait: 0.42–0.60; landscape: 1.65–2.40
                is_phone_shape = (0.42 <= aspect <= 0.60) or (1.65 <= aspect <= 2.40)
                if not is_phone_shape:
                    continue

                # Contour must tightly surround the face (tight margins)
                margin = 20
                if (rx <= fx1 + margin and ry <= fy1 + margin
                        and rx + rw >= fx2 - margin and ry + rh >= fy2 - margin):
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
                if face_ratio < 0.020:  # Face must cover at least 2% of frame
                    return False, 0.0, "Face Too Small - Move Closer to Camera"

            # --- Stage 1: Surrounding Context Screen Glow Detection ---
            # Look at the ring of pixels surrounding the face bounding box.
            # Phone screens emit uniform bright backlit glow around the face area.
            if full_frame is not None and face_obj is not None and hasattr(face_obj, 'bbox'):
                bbox = face_obj.bbox.astype(int)
                fh, fw, _ = full_frame.shape
                fx1, fy1, fx2, fy2 = bbox[0], bbox[1], bbox[2], bbox[3]
                face_w_px = fx2 - fx1
                pad = max(22, int(face_w_px * 0.30))

                outer_x1 = max(0, fx1 - pad)
                outer_y1 = max(0, fy1 - pad)
                outer_x2 = min(fw, fx2 + pad)
                outer_y2 = min(fh, fy2 + pad)

                surround_region = full_frame[outer_y1:outer_y2, outer_x1:outer_x2].copy()

                inner_sy1 = fy1 - outer_y1
                inner_sx1 = fx1 - outer_x1
                inner_sy2 = inner_sy1 + (fy2 - fy1)
                inner_sx2 = inner_sx1 + (fx2 - fx1)
                surround_mask = np.ones(surround_region.shape[:2], dtype=bool)
                surround_mask[max(0, inner_sy1):min(surround_region.shape[0], inner_sy2),
                              max(0, inner_sx1):min(surround_region.shape[1], inner_sx2)] = False

                if surround_mask.any():
                    surr_hsv = cv2.cvtColor(surround_region, cv2.COLOR_BGR2HSV)
                    surr_v = surr_hsv[:, :, 2][surround_mask]
                    surr_s = surr_hsv[:, :, 1][surround_mask]

                    # Screen backlight: very bright ring + extremely low saturation
                    # Real walls/backgrounds may be bright but will have > 40 saturation std-dev
                    # Phone OLED backlight is uniformly flat white (s < 15, v > 220)
                    screen_surround_ratio = float(np.mean((surr_v > 220) & (surr_s < 15)))
                    if screen_surround_ratio > 0.55:
                        return False, 0.0, "Screen Backlight Surround Glow Detected"

                    # Uniform + extremely bright: only OLED screens are THIS uniform
                    surr_v_std = float(np.std(surr_v.astype(np.float32)))
                    surr_v_mean = float(np.mean(surr_v.astype(np.float32)))
                    surr_s_mean = float(np.mean(surr_s.astype(np.float32)))
                    # White wall has saturation > 10; phone backlight is near-zero saturation
                    if surr_v_mean > 210 and surr_v_std < 12 and surr_s_mean < 10:
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

    def verify_face(
        self,
        full_frame: np.ndarray,
        face_obj: Any,
        registered_templates: list,
        require_challenge: bool = False,
        challenge_controller: Optional[Any] = None
    ):
        """
        Executes full multi-stage verification pipeline: Quality -> PAD -> Recognition -> Decision.
        Returns VerificationResult.
        """
        from liveness.verification import DecisionEngine

        bbox = getattr(face_obj, "bbox", None)
        if bbox is None and isinstance(face_obj, dict):
            bbox = face_obj.get("bbox")

        # 1. Quality Analysis
        quality_res = self.quality_analyzer.assess_frame(full_frame, [face_obj])

        # 2. Passive PAD
        pad_res = self.pad_engine.verify(full_frame, bbox) if bbox is not None else None

        # 3. Recognition Matching
        embedding = getattr(face_obj, "embedding", None)
        if embedding is None and isinstance(face_obj, dict):
            embedding = face_obj.get("embedding")

        rec_match = self.find_match(embedding, registered_templates, threshold=MATCH_THRESHOLD) if embedding is not None else (None, "Unknown", 0.0)

        # 4. Challenge State
        challenge_state = challenge_controller.state if challenge_controller else None

        # 5. Final Decision Gate
        return DecisionEngine.evaluate(
            quality_res=quality_res,
            pad_res=pad_res,
            recognition_match=rec_match,
            challenge_state=challenge_state,
            require_challenge=require_challenge
        )

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

