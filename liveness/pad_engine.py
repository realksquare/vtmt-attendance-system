"""
Anti-Spoofing and Presentation Attack Detection (PAD) Engine.
Integrates local ONNX MiniFASNet V2 and V1SE models for passive anti-spoofing.
Features:
- NCHW float32 BGR preprocessing with expanded 2.7x/4.0x bbox scale
- Multi-sample sliding window aggregator (MultiFramePADAggregator)
- Fail-Closed Security: Model errors or unavailable models NEVER authorize attendance (score = 0.0, passed = False)
"""

import os
import cv2
import numpy as np
import onnxruntime as ort
from typing import Tuple, List, Optional, Dict, Any
from dataclasses import dataclass, field

from config import (
    PAD_MODEL_V2_PATH,
    PAD_MODEL_V1SE_PATH,
    PAD_SCORE_THRESHOLD,
    PAD_MIN_VALID_SAMPLES
)


@dataclass
class PADResult:
    passed: bool
    score: float
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class AntiSpoofEngine:
    """
    Local ONNX MiniFASNet Passive Presentation Attack Detection (PAD) Engine.
    Evaluates 2D face presentation attacks (phone screens, tablets, printed photos, cutouts).
    """

    def __init__(
        self,
        model_path: str = PAD_MODEL_V2_PATH,
        threshold: float = PAD_SCORE_THRESHOLD,
        scale: float = 2.7,
        input_size: Tuple[int, int] = (80, 80)
    ):
        self.model_path = model_path
        self.threshold = threshold
        self.scale = scale
        self.input_size = input_size
        self.session: Optional[ort.InferenceSession] = None
        self.input_name: Optional[str] = None
        self._load_model()

    def _load_model(self):
        """Initializes the ONNX runtime inference session with CPU provider."""
        if not os.path.exists(self.model_path):
            print(f"[AntiSpoofEngine] Model not found at: {self.model_path}")
            # Fallback to secondary MiniFASNet V1SE if available
            if os.path.exists(PAD_MODEL_V1SE_PATH):
                self.model_path = PAD_MODEL_V1SE_PATH
                self.scale = 4.0
            else:
                self.session = None
                return

        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(self.model_path, opts, providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
            print(f"[AntiSpoofEngine] MiniFASNet ONNX loaded: {os.path.basename(self.model_path)}")
        except Exception as e:
            print(f"[AntiSpoofEngine] Failed to load ONNX session: {e}")
            self.session = None

    def preprocess_crop(self, full_frame: np.ndarray, bbox: np.ndarray) -> np.ndarray:
        """
        Scales face bounding box by expansion factor (e.g. 2.7x) clamped to frame boundary,
        resizes to (80, 80), converts to NCHW float32 BGR format.
        """
        fh, fw, _ = full_frame.shape
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        bw, bh = x2 - x1, y2 - y1
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        # Expanded crop dimension
        max_side = max(bw, bh)
        new_side = int(max_side * self.scale)

        nx1 = max(0, cx - new_side // 2)
        ny1 = max(0, cy - new_side // 2)
        nx2 = min(fw, cx + new_side // 2)
        ny2 = min(fh, cy + new_side // 2)

        cropped = full_frame[ny1:ny2, nx1:nx2]
        if cropped.size == 0:
            cropped = np.zeros((self.input_size[1], self.input_size[0], 3), dtype=np.uint8)
        else:
            cropped = cv2.resize(cropped, self.input_size, interpolation=cv2.INTER_AREA)

        # MiniFASNet expects [1, 3, H, W] float32 in [0, 255] or standard BGR
        blob = cropped.astype(np.float32)
        blob = np.transpose(blob, (2, 0, 1))
        blob = np.expand_dims(blob, axis=0)
        return blob

    def predict_single(self, full_frame: np.ndarray, bbox: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        """
        Executes ONNX inference on cropped face region.
        Returns (genuine_probability: float, details: dict).
        Enforces Fail-Closed security: if model is missing or fails, returns (0.0, {...})
        """
        if self.session is None:
            # Model is unavailable -> Fail Closed
            return 0.0, {
                "status": "MODEL_UNAVAILABLE",
                "error": "MiniFASNet ONNX model is missing or could not be loaded",
                "fallback": False
            }

        try:
            blob = self.preprocess_crop(full_frame, bbox)
            logits = self.session.run(None, {self.input_name: blob})[0]

            # Softmax over 3 output classes (0: attack, 1: genuine, 2: 2D attack)
            exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
            live_prob = float(probs[0][1])

            details = {
                "status": "OK",
                "model": os.path.basename(self.model_path),
                "live_score": live_prob,
                "probabilities": probs[0].tolist(),
            }
            return live_prob, details
        except Exception as err:
            print(f"[AntiSpoofEngine] Model inference error: {err}")
            # Exception in deep model -> Fail Closed
            return 0.0, {
                "status": "PAD_ERROR",
                "error": str(err),
                "fallback": False
            }

    def verify(self, full_frame: np.ndarray, bbox: np.ndarray) -> PADResult:
        """Single-frame passive PAD verification."""
        score, details = self.predict_single(full_frame, bbox)
        status = details.get("status", "OK")

        if status == "MODEL_UNAVAILABLE":
            return PADResult(
                passed=False,
                score=0.0,
                reason="PAD Model Unavailable (Fail Closed)",
                details=details
            )
        elif status == "PAD_ERROR":
            return PADResult(
                passed=False,
                score=0.0,
                reason="PAD Inference Error (Fail Closed)",
                details=details
            )

        passed = score >= self.threshold
        reason = "Genuine Live Face" if passed else f"Presentation Attack / Spoof Detected (PAD: {score:.2f} < {self.threshold:.2f})"
        return PADResult(passed=passed, score=score, reason=reason, details=details)


class MultiFramePADAggregator:
    """
    Aggregates passive PAD scores over multiple temporal observations
    to enforce multi-frame statistical consistency and prevent single-frame false acceptance.
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
        if len(self.samples) == 0:
            return PADResult(
                passed=False,
                score=0.0,
                reason="No PAD samples collected",
                details={"sample_count": 0}
            )

        if len(self.samples) < self.min_samples:
            median_score = float(np.median(self.samples))
            return PADResult(
                passed=False,
                score=median_score,
                reason=f"Insufficient temporal PAD samples ({len(self.samples)} < {self.min_samples} required)",
                details={"sample_count": len(self.samples), "min_required": self.min_samples}
            )

        # Calculate statistics
        median_score = float(np.median(self.samples))
        mean_score = float(np.mean(self.samples))
        min_score = float(np.min(self.samples))
        max_score = float(np.max(self.samples))
        std_dev = float(np.std(self.samples))

        # Fail closed if any sample encountered a model error
        has_error = any(d.get("status") in ("MODEL_UNAVAILABLE", "PAD_ERROR") for d in self.sample_details)
        if has_error:
            return PADResult(
                passed=False,
                score=0.0,
                reason="PAD model error encountered in temporal sequence (Fail Closed)",
                details={"sample_count": len(self.samples), "has_error": True}
            )

        passed = (median_score >= self.threshold) and (min_score >= (self.threshold - 0.20))
        reason = "Multi-Frame Live Verification Passed" if passed else f"Multi-Frame Spoof Rejected (Median: {median_score:.2f} < {self.threshold:.2f})"

        return PADResult(
            passed=passed,
            score=median_score,
            reason=reason,
            details={
                "sample_count": len(self.samples),
                "median_score": median_score,
                "mean_score": mean_score,
                "min_score": min_score,
                "max_score": max_score,
                "std_dev": std_dev
            }
        )
