"""
Face Quality Analyzer Module.
Filters low-quality, blurry, under/over-exposed, cut-off, or multi-face presentations
before expensive PAD and face recognition processing.
"""

from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import numpy as np
import cv2

from config import QUALITY_MIN_FACE_AREA_RATIO, QUALITY_BLUR_THRESHOLD


@dataclass
class QualityResult:
    passed: bool
    reason: str
    blur_score: float = 0.0
    area_ratio: float = 0.0
    brightness_mean: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class FaceQualityAnalyzer:
    """
    Evaluates face image quality metrics:
    - Face count constraint (exactly 1 face in session)
    - Face-to-frame area ratio
    - Boundary completeness (margin from edge)
    - Sharpness via Laplacian variance
    - Lighting / exposure distribution
    - Extreme head pose check
    """

    def __init__(
        self,
        min_area_ratio: float = QUALITY_MIN_FACE_AREA_RATIO,
        blur_threshold: float = QUALITY_BLUR_THRESHOLD,
        min_brightness: float = 35.0,
        max_brightness: float = 235.0
    ):
        self.min_area_ratio = min_area_ratio
        self.blur_threshold = blur_threshold
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness

    def assess_frame(
        self,
        full_frame: np.ndarray,
        faces: List[Any]
    ) -> QualityResult:
        """
        Assesses entire frame and detected faces list against quality constraints.
        """
        if full_frame is None or full_frame.size == 0:
            return QualityResult(passed=False, reason="Empty camera frame")

        fh, fw, _ = full_frame.shape
        frame_area = float(fh * fw)

        # 1. Face count constraint
        if len(faces) == 0:
            return QualityResult(passed=False, reason="No face detected. Please position your face clearly.")
        elif len(faces) > 1:
            return QualityResult(
                passed=False,
                reason=f"Multiple faces detected ({len(faces)}). Please ensure only ONE person is in view."
            )

        face = faces[0]
        bbox = face.bbox if hasattr(face, "bbox") else face.get("bbox")
        if bbox is None or len(bbox) < 4:
            return QualityResult(passed=False, reason="Invalid face bounding box")

        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        bw = max(0, x2 - x1)
        bh = max(0, y2 - y1)
        face_area = float(bw * bh)
        area_ratio = face_area / (frame_area + 1e-5)

        # 2. Minimum face size ratio
        if area_ratio < self.min_area_ratio or bw < 40 or bh < 40:
            return QualityResult(
                passed=False,
                area_ratio=area_ratio,
                reason="Face too small. Please move closer to the camera."
            )

        # 3. Boundary margin (not cut off at frame borders)
        margin = 10
        if x1 < margin or y1 < margin or x2 > (fw - margin) or y2 > (fh - margin):
            return QualityResult(
                passed=False,
                area_ratio=area_ratio,
                reason="Face cut off at frame border. Please center your face."
            )

        # 4. Crop face region for texture and lighting analysis
        cx1, cy1, cx2, cy2 = max(0, x1), max(0, y1), min(fw, x2), min(fh, y2)
        face_crop = full_frame[cy1:cy2, cx1:cx2]
        if face_crop.size == 0:
            return QualityResult(passed=False, reason="Invalid face crop")

        gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

        # 5. Sharpness (Laplacian variance)
        blur_score = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
        if blur_score < self.blur_threshold:
            return QualityResult(
                passed=False,
                blur_score=blur_score,
                area_ratio=area_ratio,
                reason=f"Image too blurry (Score: {blur_score:.1f} < {self.blur_threshold:.1f}). Hold still."
            )

        # 6. Lighting / Exposure distribution
        brightness_mean = float(np.mean(gray_crop))
        if brightness_mean < self.min_brightness:
            return QualityResult(
                passed=False,
                blur_score=blur_score,
                area_ratio=area_ratio,
                brightness_mean=brightness_mean,
                reason="Lighting too dark. Please face towards light."
            )
        elif brightness_mean > self.max_brightness:
            return QualityResult(
                passed=False,
                blur_score=blur_score,
                area_ratio=area_ratio,
                brightness_mean=brightness_mean,
                reason="Lighting over-exposed / glaring. Please adjust lighting."
            )

        # 7. Extreme pose check if pose metadata is attached
        pose = getattr(face, "pose", None) or (face.get("pose") if isinstance(face, dict) else None)
        if pose is not None and len(pose) >= 3:
            pitch, yaw, roll = abs(float(pose[0])), abs(float(pose[1])), abs(float(pose[2]))
            if pitch > 40.0 or roll > 35.0:
                return QualityResult(
                    passed=False,
                    blur_score=blur_score,
                    area_ratio=area_ratio,
                    brightness_mean=brightness_mean,
                    reason="Extreme head tilt. Please look straight at the camera."
                )

        return QualityResult(
            passed=True,
            reason="Face Quality Passed",
            blur_score=blur_score,
            area_ratio=area_ratio,
            brightness_mean=brightness_mean,
            details={
                "area_ratio": area_ratio,
                "blur_score": blur_score,
                "brightness_mean": brightness_mean,
                "bbox": [x1, y1, x2, y2]
            }
        )
