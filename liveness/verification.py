"""
Verification Session and Final Decision Engine.
Enforces strict fail-closed security decision logic combining Quality, Passive PAD,
Active Challenge-Response, and Independent Face Recognition before attendance authorization.
"""

import time
import uuid
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

from .quality import QualityResult
from .pad_engine import PADResult
from .challenge import ChallengeState


class ReasonCode(str, Enum):
    SUCCESS = "SUCCESS"
    NO_FACE = "NO_FACE"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    LOW_FACE_QUALITY = "LOW_FACE_QUALITY"
    LOW_LIGHT = "LOW_LIGHT"
    EXCESSIVE_BLUR = "EXCESSIVE_BLUR"
    PAD_SPOOF = "PAD_SPOOF"
    PAD_LOW_CONFIDENCE = "PAD_LOW_CONFIDENCE"
    CHALLENGE_TIMEOUT = "CHALLENGE_TIMEOUT"
    CHALLENGE_FAILED = "CHALLENGE_FAILED"
    TEMPORAL_INCONSISTENCY = "TEMPORAL_INCONSISTENCY"
    UNKNOWN_PERSON = "UNKNOWN_PERSON"
    LOW_RECOGNITION_SCORE = "LOW_RECOGNITION_SCORE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass
class VerificationResult:
    authorized: bool
    reason_code: ReasonCode
    message: str
    identity: Optional[str] = None
    student_name: Optional[str] = None
    recognition_score: float = 0.0
    pad_score: float = 0.0
    quality_passed: bool = False
    pad_passed: bool = False
    challenge_passed: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class DecisionEngine:
    """
    Final security authorization gate.
    Evaluates independent pipeline components and enforces fail-closed rules:
    - High recognition score CANNOT bypass PAD or Challenge failure.
    - Missing or failed components immediately reject authorization.
    """

    @staticmethod
    def evaluate(
        quality_res: QualityResult,
        pad_res: PADResult,
        recognition_match: Tuple[Optional[str], str, float],
        challenge_state: Optional[ChallengeState] = None,
        require_challenge: bool = False
    ) -> VerificationResult:
        student_id, student_name, rec_score = recognition_match

        details = {
            "quality_details": quality_res.details if quality_res else {},
            "pad_details": pad_res.details if pad_res else {},
            "recognition_score": float(rec_score),
            "challenge_state": str(challenge_state) if challenge_state else "BYPASSED",
        }

        # 1. Quality Gate
        if quality_res is None or not quality_res.passed:
            reason_code = ReasonCode.LOW_FACE_QUALITY
            if quality_res and "Multiple" in quality_res.reason:
                reason_code = ReasonCode.MULTIPLE_FACES
            elif quality_res and "No face" in quality_res.reason:
                reason_code = ReasonCode.NO_FACE
            elif quality_res and "dark" in quality_res.reason.lower():
                reason_code = ReasonCode.LOW_LIGHT
            elif quality_res and "blurry" in quality_res.reason.lower():
                reason_code = ReasonCode.EXCESSIVE_BLUR

            return VerificationResult(
                authorized=False,
                reason_code=reason_code,
                message=quality_res.reason if quality_res else "Quality check failed",
                quality_passed=False,
                pad_passed=pad_res.passed if pad_res else False,
                details=details
            )

        # 2. Passive PAD Gate
        if pad_res is None or not pad_res.passed:
            return VerificationResult(
                authorized=False,
                reason_code=ReasonCode.PAD_SPOOF,
                message=pad_res.reason if pad_res else "Anti-spoofing verification failed",
                quality_passed=True,
                pad_passed=False,
                pad_score=pad_res.score if pad_res else 0.0,
                details=details
            )

        # 3. Active Challenge Gate (if required for interactive mode)
        challenge_passed = True
        if require_challenge:
            if challenge_state != ChallengeState.COMPLETED:
                challenge_passed = False
                reason_code = ReasonCode.CHALLENGE_TIMEOUT if challenge_state == ChallengeState.FAILED else ReasonCode.CHALLENGE_FAILED
                return VerificationResult(
                    authorized=False,
                    reason_code=reason_code,
                    message="Active challenge verification incomplete or failed",
                    quality_passed=True,
                    pad_passed=True,
                    challenge_passed=False,
                    pad_score=pad_res.score,
                    details=details
                )

        # 4. Recognition Gate
        if not student_id or student_id is None:
            return VerificationResult(
                authorized=False,
                reason_code=ReasonCode.UNKNOWN_PERSON,
                message=f"Unrecognized student face (Confidence: {rec_score:.2f})",
                quality_passed=True,
                pad_passed=True,
                challenge_passed=challenge_passed,
                recognition_score=rec_score,
                pad_score=pad_res.score,
                identity=None,
                student_name="Unknown",
                details=details
            )

        # ALL GATES PASSED -> Authorize attendance commit
        return VerificationResult(
            authorized=True,
            reason_code=ReasonCode.SUCCESS,
            message=f"Verification successful for {student_name} ({student_id})",
            identity=student_id,
            student_name=student_name,
            recognition_score=rec_score,
            pad_score=pad_res.score,
            quality_passed=True,
            pad_passed=True,
            challenge_passed=challenge_passed,
            details=details
        )


class VerificationSession:
    """
    Manages state for an active multi-frame verification session.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.start_time = time.time()
        self.frame_count: int = 0
        self.quality_passed: bool = False
        self.pad_passed: bool = False
        self.challenge_passed: bool = False
        self.final_result: Optional[VerificationResult] = None

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time
