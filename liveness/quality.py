"""
Face Quality Analyzer Module.
Implements a 3-Tier Quality Hierarchy for Classroom and Individual Face Analysis:
- RECOGNITION_SAFE: Clear, sufficiently large face suitable for biometric recognition & PAD.
- TRACKABLE_BUT_SMALL: Detectable face (e.g. back row student) suitable for tracking and evidence accumulation.
- UNUSABLE: Insufficient information, severe blur, or out-of-bounds face.
"""

from enum import Enum
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import numpy as np
import cv2

from config import (
    QUALITY_MIN_FACE_AREA_RATIO,
    QUALITY_TRACKABLE_MIN_AREA_RATIO,
    QUALITY_BLUR_THRESHOLD,
    QUALITY_TRACKABLE_BLUR_THRESHOLD,
    QUALITY_MIN_BRIGHTNESS,
    QUALITY_MAX_BRIGHTNESS
)


class QualityTier(str, Enum):
    RECOGNITION_SAFE = "RECOGNITION_SAFE"
    TRACKABLE_BUT_SMALL = "TRACKABLE_BUT_SMALL"
    UNUSABLE = "UNUSABLE"


@dataclass
class QualityResult:
    passed: bool
    reason: str
    tier: QualityTier = QualityTier.UNUSABLE
    blur_score: float = 0.0
    area_ratio: float = 0.0
    brightness_mean: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class FaceQualityAnalyzer:
    """
    Evaluates individual face quality metrics against calibrated classroom tiers:
    - Minimum face size ratio (safe vs trackable vs unusable)
    - Boundary margin completeness (not cut off at frame border)
    - Sharpness via Laplacian variance
    - Lighting / exposure distribution
    - Extreme head pose angles
    - Single-face constraint (optional for 1-on-1 enrollment, bypassed in classroom mode)
    """

    def __init__(
        self,
        min_safe_area_ratio: float = QUALITY_MIN_FACE_AREA_RATIO,
        min_trackable_area_ratio: float = QUALITY_TRACKABLE_MIN_AREA_RATIO,
        safe_blur_threshold: float = QUALITY_BLUR_THRESHOLD,
        trackable_blur_threshold: float = QUALITY_TRACKABLE_BLUR_THRESHOLD,
        min_brightness: float = QUALITY_MIN_BRIGHTNESS,
        max_brightness: float = QUALITY_MAX_BRIGHTNESS
    ):
        self.min_safe_area_ratio = min_safe_area_ratio
        self.min_trackable_area_ratio = min_trackable_area_ratio
        self.safe_blur_threshold = safe_blur_threshold
        self.trackable_blur_threshold = trackable_blur_threshold
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness

    def assess_face(
        self,
        full_frame: np.ndarray,
        face_obj: Any
    ) -> QualityResult:
        """
        Assesses a single face object within a frame into a 3-tier quality classification.
        """
        if full_frame is None or full_frame.size == 0 or face_obj is None:
            return QualityResult(passed=False, reason="Empty frame or null face", tier=QualityTier.UNUSABLE)

        fh, fw, _ = full_frame.shape
        frame_area = float(fh * fw)

        # Extract bounding box safely
        bbox = None
        if hasattr(face_obj, "bbox"):
            bbox = getattr(face_obj, "bbox")
        elif isinstance(face_obj, dict):
            bbox = face_obj.get("bbox")

        if bbox is None or len(bbox) < 4:
            return QualityResult(passed=False, reason="Invalid face bounding box", tier=QualityTier.UNUSABLE)

        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        bw = max(0, x2 - x1)
        bh = max(0, y2 - y1)
        face_area = float(bw * bh)
        area_ratio = face_area / (frame_area + 1e-5)

        # Boundary margin check
        margin = 6
        is_cut_off = (x1 < margin or y1 < margin or x2 > (fw - margin) or y2 > (fh - margin))
        if is_cut_off and area_ratio < self.min_trackable_area_ratio:
            return QualityResult(
                passed=False,
                reason="Face cut off at frame border",
                tier=QualityTier.UNUSABLE,
                area_ratio=area_ratio
            )

        # Crop face region for texture, blur, and lighting analysis
        cx1, cy1, cx2, cy2 = max(0, x1), max(0, y1), min(fw, x2), min(fh, y2)
        face_crop = full_frame[cy1:cy2, cx1:cx2]
        if face_crop.size == 0:
            return QualityResult(passed=False, reason="Invalid face crop size", tier=QualityTier.UNUSABLE)

        gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

        # Sharpness (Laplacian variance)
        blur_score = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())

        # Lighting / Exposure distribution
        brightness_mean = float(np.mean(gray_crop))

        details = {
            "bbox": [x1, y1, x2, y2],
            "area_ratio": area_ratio,
            "blur_score": blur_score,
            "brightness_mean": brightness_mean,
            "is_cut_off": is_cut_off
        }

        # Check for extreme lighting / exposure
        if brightness_mean < self.min_brightness:
            return QualityResult(
                passed=False,
                reason="Lighting too dark. Face poorly illuminated.",
                tier=QualityTier.UNUSABLE,
                blur_score=blur_score,
                area_ratio=area_ratio,
                brightness_mean=brightness_mean,
                details=details
            )
        elif brightness_mean > self.max_brightness:
            return QualityResult(
                passed=False,
                reason="Lighting over-exposed / severe glare.",
                tier=QualityTier.UNUSABLE,
                blur_score=blur_score,
                area_ratio=area_ratio,
                brightness_mean=brightness_mean,
                details=details
            )

        # Pose check if pose is attached
        pose = None
        if hasattr(face_obj, "pose"):
            pose = getattr(face_obj, "pose")
        elif isinstance(face_obj, dict):
            pose = face_obj.get("pose")

        extreme_pose = False
        if pose is not None and len(pose) >= 3:
            pitch, yaw, roll = abs(float(pose[0])), abs(float(pose[1])), abs(float(pose[2]))
            details["pose"] = [pitch, yaw, roll]
            if pitch > 42.0 or roll > 38.0 or yaw > 50.0:
                extreme_pose = True

        # Classify into 3 Tiers:
        # 1. UNUSABLE
        if (
            area_ratio < self.min_trackable_area_ratio
            or blur_score < self.trackable_blur_threshold
            or extreme_pose
        ):
            reason_msg = "Face too blurry or tiny" if blur_score < self.trackable_blur_threshold else "Face too small / unusable"
            if extreme_pose:
                reason_msg = "Extreme head pose angle"
            return QualityResult(
                passed=False,
                reason=reason_msg,
                tier=QualityTier.UNUSABLE,
                blur_score=blur_score,
                area_ratio=area_ratio,
                brightness_mean=brightness_mean,
                details=details
            )

        # 2. TRACKABLE_BUT_SMALL (e.g. Back/Middle row in classroom)
        if (
            area_ratio < self.min_safe_area_ratio
            or blur_score < self.safe_blur_threshold
            or is_cut_off
        ):
            return QualityResult(
                passed=True,
                reason="Trackable small/distant face",
                tier=QualityTier.TRACKABLE_BUT_SMALL,
                blur_score=blur_score,
                area_ratio=area_ratio,
                brightness_mean=brightness_mean,
                details=details
            )

        # 3. RECOGNITION_SAFE
        return QualityResult(
            passed=True,
            reason="Face Quality Safe for Biometric Recognition",
            tier=QualityTier.RECOGNITION_SAFE,
            blur_score=blur_score,
            area_ratio=area_ratio,
            brightness_mean=brightness_mean,
            details=details
        )

    def assess_frame(
        self,
        full_frame: np.ndarray,
        faces: List[Any],
        enforce_single_face: bool = False
    ) -> QualityResult:
        """
        Assesses entire frame and detected faces list.
        enforce_single_face: Set True for 1-on-1 enrollment or active challenge.
                             Set False for classroom multi-student burst capture.
        """
        if full_frame is None or full_frame.size == 0:
            return QualityResult(passed=False, reason="Empty camera frame", tier=QualityTier.UNUSABLE)

        if len(faces) == 0:
            return QualityResult(passed=False, reason="No face detected in view", tier=QualityTier.UNUSABLE)

        if enforce_single_face and len(faces) > 1:
            return QualityResult(
                passed=False,
                reason=f"Multiple faces detected ({len(faces)}). Please ensure only ONE person is in view for enrollment.",
                tier=QualityTier.UNUSABLE
            )

        # In multi-student or single-face mode, assess the primary/first face
        return self.assess_face(full_frame, faces[0])
