"""
Passive Presentation Attack Detection (PAD) Engine.
Integrates local MiniFASNet ONNX model inference and multi-frame sample aggregation.
"""

import os
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import numpy as np
import cv2
import onnxruntime as ort

from config import (
    PAD_MODEL_V2_PATH, PAD_MODEL_V1SE_PATH, PAD_SCORE_THRESHOLD, PAD_MIN_VALID_SAMPLES
)


@dataclass
class PADResult:
    passed: bool
    score: float
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class AntiSpoofEngine:
    """
    Local ONNX-based Passive Presentation Attack Detection Engine.
    Executes MiniFASNet V2 / V1SE inference on expanded face crops.
    """

    def __init__(self, model_path: str = PAD_MODEL_V2_PATH, threshold: float = PAD_SCORE_THRESHOLD):
        self.threshold = threshold
        self.model_path = model_path
        self.session: Optional[ort.InferenceSession] = None
        self.input_name: str = "input"
        self.input_shape: Tuple[int, int] = (80, 80)
        self.crop_scale: float = 2.7

        self._load_model()

    def _load_model(self):
        """Initialize local ONNX Runtime inference session on CPU."""
        if not os.path.exists(self.model_path):
            # Fallback to secondary model if primary path not found
            if os.path.exists(PAD_MODEL_V1SE_PATH):
                self.model_path = PAD_MODEL_V1SE_PATH
                self.crop_scale = 4.0

        if os.path.exists(self.model_path):
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.inter_op_num_threads = 1
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(self.model_path, opts, providers=["CPUExecutionProvider"])
            inputs = self.session.get_inputs()
            if inputs:
                self.input_name = inputs[0].name
                # Shape format: [batch, channels, height, width]
                if len(inputs[0].shape) == 4 and isinstance(inputs[0].shape[2], int):
                    self.input_shape = (inputs[0].shape[2], inputs[0].shape[3])

    def preprocess_crop(self, full_frame: np.ndarray, bbox: np.ndarray) -> np.ndarray:
        """
        Extracts scaled bounding box crop clamped to frame boundary and formats to NCHW float32.
        """
        fh, fw, _ = full_frame.shape
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        bw = x2 - x1
        bh = y2 - y1
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        # Expanded crop based on model scale factor (e.g. 2.7x)
        crop_w = bw * self.crop_scale
        crop_h = bh * self.crop_scale

        nx1 = max(0, int(cx - crop_w / 2.0))
        ny1 = max(0, int(cy - crop_h / 2.0))
        nx2 = min(fw, int(cx + crop_w / 2.0))
        ny2 = min(fh, int(cy + crop_h / 2.0))

        if nx2 <= nx1 or ny2 <= ny1:
            crop = cv2.resize(full_frame[max(0, y1):min(fh, y2), max(0, x1):min(fw, x2)], self.input_shape)
        else:
            crop = full_frame[ny1:ny2, nx1:nx2]
            crop = cv2.resize(crop, self.input_shape)

        # Transpose HWC (BGR) to CHW and add batch dim
        blob = crop.astype(np.float32)
        blob = np.transpose(blob, (2, 0, 1))
        blob = np.expand_dims(blob, axis=0)
        return blob

    def predict_single(self, full_frame: np.ndarray, bbox: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        """
        Runs MiniFASNet inference on face crop.
        Returns genuine live score probability in [0.0, 1.0].
        """
        if self.session is None:
            # If model file is unavailable, run local spectral analyzer
            return self._spectral_fallback(full_frame, bbox)

        try:
            blob = self.preprocess_crop(full_frame, bbox)
            logits = self.session.run(None, {self.input_name: blob})[0]

            # Softmax over 3 output classes (0: attack, 1: genuine, 2: 2D attack)
            exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
            live_prob = float(probs[0][1])

            details = {
                "model": os.path.basename(self.model_path),
                "live_score": live_prob,
                "probabilities": probs[0].tolist(),
            }
            return live_prob, details
        except Exception as err:
            print(f"[AntiSpoofEngine] Model inference error: {err}")
            return self._spectral_fallback(full_frame, bbox)

    def _spectral_fallback(self, full_frame: np.ndarray, bbox: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        """
        Deterministic spectral texture fallback analyzing Moiré frequency,
        dermal chroma, and glass reflections when deep model is unavailable.
        """
        fh, fw, _ = full_frame.shape
        x1, y1, x2, y2 = max(0, int(bbox[0])), max(0, int(bbox[1])), min(fw, int(bbox[2])), min(fh, int(bbox[3]))
        face_crop = full_frame[y1:y2, x1:x2]

        if face_crop.size == 0:
            return 0.0, {"reason": "Empty crop"}

        h, w, _ = face_crop.shape
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

        # 2D FFT Moiré high frequency ratio
        f = np.fft.fft2(gray)
        fshift = np.fft.fftshift(f)
        mag = 20 * np.log(np.abs(fshift) + 1e-5)
        cy, cx = h // 2, w // 2
        r_low = max(5, min(h, w) // 8)
        low_energy = mag[max(0, cy - r_low):min(h, cy + r_low), max(0, cx - r_low):min(w, cx + r_low)].mean()
        high_freq_ratio = float(mag.mean() / (low_energy + 1e-5))

        # YCrCb dermal skin chroma
        ycrcb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2YCrCb)
        cr, cb = ycrcb[:, :, 1], ycrcb[:, :, 2]
        skin_ratio = float(np.count_nonzero((cr >= 128) & (cr <= 175) & (cb >= 75) & (cb <= 132))) / float(h * w)

        # Specular screen glare
        hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
        glare_ratio = float(np.count_nonzero((hsv[:, :, 2] > 240) & (hsv[:, :, 1] < 30))) / float(h * w)

        is_spoof = (high_freq_ratio > 0.76) or (glare_ratio > 0.06) or (skin_ratio < 0.20)
        score = 0.20 if is_spoof else 0.85

        return score, {
            "fallback": True,
            "high_freq_ratio": high_freq_ratio,
            "skin_ratio": skin_ratio,
            "glare_ratio": glare_ratio
        }

    def verify(self, full_frame: np.ndarray, bbox: np.ndarray) -> PADResult:
        """Single-frame passive PAD verification."""
        score, details = self.predict_single(full_frame, bbox)
        passed = score >= self.threshold
        reason = "Genuine Live Face" if passed else "Presentation Attack / Spoof Detected"
        return PADResult(passed=passed, score=score, reason=reason, details=details)


class MultiFramePADAggregator:
    """
    Aggregates passive PAD scores over multiple temporal samples
    to prevent single-frame false acceptances or rejections.
    """

    def __init__(self, min_samples: int = PAD_MIN_VALID_SAMPLES, threshold: float = PAD_SCORE_THRESHOLD):
        self.min_samples = min_samples
        self.threshold = threshold
        self.samples: List[float] = []
        self.sample_details: List[Dict[str, Any]] = []

    def reset(self):
        """Clears accumulated samples for a new session."""
        self.samples.clear()
        self.sample_details.clear()

    def add_sample(self, score: float, details: Optional[Dict[str, Any]] = None):
        """Appends a valid PAD score sample."""
        self.samples.append(float(score))
        if details:
            self.sample_details.append(details)

    def evaluate(self) -> PADResult:
        """
        Computes robust aggregate statistics (median, min, max, std)
        and evaluates final multi-frame PAD decision.
        """
        count = len(self.samples)
        if count < self.min_samples:
            return PADResult(
                passed=False,
                score=float(np.median(self.samples)) if count > 0 else 0.0,
                reason=f"Insufficient PAD Samples ({count}/{self.min_samples})",
                details={"sample_count": count, "samples": list(self.samples)}
            )

        median_score = float(np.median(self.samples))
        min_score = float(np.min(self.samples))
        max_score = float(np.max(self.samples))
        std_score = float(np.std(self.samples))

        passed = median_score >= self.threshold
        reason = "Multi-Frame PAD Passed" if passed else f"Multi-Frame PAD Failed (Median: {median_score:.2f} < {self.threshold:.2f})"

        return PADResult(
            passed=passed,
            score=median_score,
            reason=reason,
            details={
                "sample_count": count,
                "median_score": median_score,
                "min_score": min_score,
                "max_score": max_score,
                "std_score": std_score,
                "samples": list(self.samples)
            }
        )
