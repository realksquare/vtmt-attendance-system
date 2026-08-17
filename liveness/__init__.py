"""
Liveness and Presentation Attack Detection (PAD) Package.
Implements multi-stage hybrid offline verification:
- Face Quality Analysis
- Passive Anti-Spoofing (MiniFASNet ONNX)
- Randomized Active Challenge-Response (Head Turn, Blink)
- Temporal Validation & Fail-Closed Decision Engine
"""

from .quality import FaceQualityAnalyzer, QualityResult
from .pad_engine import AntiSpoofEngine, MultiFramePADAggregator, PADResult
from .challenge import LivenessChallengeController, ChallengeAction, ChallengeState
from .verification import VerificationSession, DecisionEngine, VerificationResult, ReasonCode

__all__ = [
    "FaceQualityAnalyzer",
    "QualityResult",
    "AntiSpoofEngine",
    "MultiFramePADAggregator",
    "PADResult",
    "LivenessChallengeController",
    "ChallengeAction",
    "ChallengeState",
    "VerificationSession",
    "DecisionEngine",
    "VerificationResult",
    "ReasonCode",
]
