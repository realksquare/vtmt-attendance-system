"""
Liveness and Presentation Attack Detection (PAD) Package.
Implements multi-stage hybrid offline verification:
- Face Quality Analysis
- Passive Anti-Spoofing (MiniFASNet ONNX)
- Randomized Active Challenge-Response (Head Turn, Blink)
- Temporal Validation & Fail-Closed Decision Engine
"""

from .quality import FaceQualityAnalyzer, QualityResult, QualityTier
from .pad_engine import AntiSpoofEngine, MultiFramePADAggregator, PADResult
from .challenge import LivenessChallengeController, ChallengeAction, ChallengeState
from .verification import VerificationSession, DecisionEngine, VerificationResult, ReasonCode
from .tracker import ClassroomFaceTracker, BurstDecisionAggregator, TrackEvidence, TrackDecision, FaceObservation

__all__ = [
    "FaceQualityAnalyzer",
    "QualityResult",
    "QualityTier",
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
    "ClassroomFaceTracker",
    "BurstDecisionAggregator",
    "TrackEvidence",
    "TrackDecision",
    "FaceObservation",
]
