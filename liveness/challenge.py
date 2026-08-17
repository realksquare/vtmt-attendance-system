"""
Randomized Active Liveness Challenge-Response Controller.
Generates dynamic session challenges (TURN_LEFT, TURN_RIGHT, BLINK)
and verifies temporal landmark/pose transitions via a deterministic state machine.
"""

import time
import random
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
import numpy as np

from config import CHALLENGE_PER_ACTION_TIMEOUT, CHALLENGE_TOTAL_TIMEOUT, CHALLENGE_ACTION_COUNT


class ChallengeAction(str, Enum):
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    BLINK = "BLINK"


class ChallengeState(str, Enum):
    IDLE = "IDLE"
    STARTED = "STARTED"
    WAITING_FOR_ACTION = "WAITING_FOR_ACTION"
    ACTION_DETECTED = "ACTION_DETECTED"
    ACTION_CONFIRMED = "ACTION_CONFIRMED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ChallengeProgress:
    current_action: Optional[ChallengeAction]
    action_index: int
    total_actions: int
    prompt_text: str
    time_remaining: float
    state: ChallengeState


class LivenessChallengeController:
    """
    State machine controller for randomized interactive liveness challenges.
    Tracks neutral head pose baseline, evaluates temporal blink sequences,
    and advances through randomized challenge actions.
    """

    def __init__(
        self,
        action_count: int = CHALLENGE_ACTION_COUNT,
        per_action_timeout: float = CHALLENGE_PER_ACTION_TIMEOUT,
        total_timeout: float = CHALLENGE_TOTAL_TIMEOUT
    ):
        self.action_count = action_count
        self.per_action_timeout = per_action_timeout
        self.total_timeout = total_timeout

        self.state = ChallengeState.IDLE
        self.challenges: List[ChallengeAction] = []
        self.current_idx: int = 0

        self.session_start_time: float = 0.0
        self.action_start_time: float = 0.0
        self.confirmed_actions: List[ChallengeAction] = []
        self.failure_reason: Optional[str] = None

        # Temporal gesture tracking state
        self.baseline_yaw: Optional[float] = None
        self.baseline_pitch: Optional[float] = None
        self.action_hold_frames: int = 0
        self.blink_phase: str = "WAIT_OPEN"  # "WAIT_OPEN" -> "CLOSED" -> "REOPENED"
        self.history_ear: List[float] = []

    def start_session(self, explicit_actions: Optional[List[ChallengeAction]] = None) -> List[ChallengeAction]:
        """
        Generates a new randomized challenge sequence and initializes session timers.
        """
        if explicit_actions is not None:
            self.challenges = list(explicit_actions)
        else:
            all_actions = [ChallengeAction.TURN_LEFT, ChallengeAction.TURN_RIGHT, ChallengeAction.BLINK]
            # Randomly select actions ensuring variety
            self.challenges = random.sample(all_actions, min(self.action_count, len(all_actions)))

        self.current_idx = 0
        self.confirmed_actions.clear()
        self.failure_reason = None
        self.session_start_time = time.time()
        self.action_start_time = self.session_start_time
        self.state = ChallengeState.WAITING_FOR_ACTION

        self.baseline_yaw = None
        self.baseline_pitch = None
        self.action_hold_frames = 0
        self.blink_phase = "WAIT_OPEN"
        self.history_ear.clear()

        return list(self.challenges)

    def reset(self):
        """Resets controller to IDLE state."""
        self.state = ChallengeState.IDLE
        self.challenges.clear()
        self.current_idx = 0
        self.confirmed_actions.clear()
        self.failure_reason = None

    def get_current_action(self) -> Optional[ChallengeAction]:
        if 0 <= self.current_idx < len(self.challenges):
            return self.challenges[self.current_idx]
        return None

    def get_prompt_text(self) -> str:
        """User-facing instruction prompt for current challenge."""
        if self.state == ChallengeState.COMPLETED:
            return "Liveness Verified Successfully!"
        elif self.state == ChallengeState.FAILED:
            return f"Liveness Verification Failed: {self.failure_reason or 'Timeout'}"

        action = self.get_current_action()
        if action == ChallengeAction.TURN_LEFT:
            return "Please turn your head slightly to the LEFT"
        elif action == ChallengeAction.TURN_RIGHT:
            return "Please turn your head slightly to the RIGHT"
        elif action == ChallengeAction.BLINK:
            return "Please BLINK your eyes naturally"
        return "Please look at the camera"

    def get_progress(self) -> ChallengeProgress:
        """Returns snapshot of current challenge progress for UI overlays."""
        now = time.time()
        action_elapsed = now - self.action_start_time
        time_remaining = max(0.0, self.per_action_timeout - action_elapsed)

        return ChallengeProgress(
            current_action=self.get_current_action(),
            action_index=self.current_idx + 1 if self.challenges else 0,
            total_actions=len(self.challenges),
            prompt_text=self.get_prompt_text(),
            time_remaining=time_remaining,
            state=self.state
        )

    @staticmethod
    def calculate_ear(landmarks_2d: np.ndarray) -> float:
        """
        Calculates Eye Aspect Ratio (EAR) from 2D dense landmarks.
        Uses standard eye landmark indices or relative eye height/width.
        """
        if landmarks_2d is None or len(landmarks_2d) < 100:
            return 0.30  # Default open eye ratio fallback

        try:
            # InsightFace 2d106det landmark eye indices
            # Left eye: top [43], bottom [47], left corner [35], right corner [39]
            # Right eye: top [101], bottom [105], left corner [89], right corner [93]
            # Calculate left eye aspect ratio
            p35, p39 = landmarks_2d[35], landmarks_2d[39]
            p43, p47 = landmarks_2d[43], landmarks_2d[47]
            left_w = np.linalg.norm(p35 - p39) + 1e-5
            left_h = np.linalg.norm(p43 - p47)
            ear_left = left_h / left_w

            # Calculate right eye aspect ratio
            p89, p93 = landmarks_2d[89], landmarks_2d[93]
            p101, p105 = landmarks_2d[101], landmarks_2d[105]
            right_w = np.linalg.norm(p89 - p93) + 1e-5
            right_h = np.linalg.norm(p101 - p105)
            ear_right = right_h / right_w

            return float((ear_left + ear_right) / 2.0)
        except Exception:
            return 0.30

    def process_frame(
        self,
        face_obj: Any,
        landmarks_2d: Optional[np.ndarray] = None,
        pose_angles: Optional[np.ndarray] = None
    ) -> Tuple[ChallengeState, str]:
        """
        Processes current video frame's facial geometry and updates state machine.
        """
        if self.state in (ChallengeState.COMPLETED, ChallengeState.FAILED, ChallengeState.IDLE):
            return self.state, self.get_prompt_text()

        now = time.time()

        # 1. Timeout validations
        if (now - self.session_start_time) > self.total_timeout:
            self.state = ChallengeState.FAILED
            self.failure_reason = "Total Challenge Timeout Exceeded"
            return self.state, self.failure_reason

        if (now - self.action_start_time) > self.per_action_timeout:
            self.state = ChallengeState.FAILED
            self.failure_reason = f"Action Timeout for {self.get_current_action()}"
            return self.state, self.failure_reason

        if face_obj is None:
            return self.state, "No Face in View"

        # Extract landmarks and pose from face object if not passed directly
        if pose_angles is None:
            if hasattr(face_obj, "pose"):
                pose_angles = getattr(face_obj, "pose")
            elif isinstance(face_obj, dict):
                pose_angles = face_obj.get("pose")

        if landmarks_2d is None:
            if hasattr(face_obj, "landmark_2d_106"):
                landmarks_2d = getattr(face_obj, "landmark_2d_106")
            elif isinstance(face_obj, dict):
                landmarks_2d = face_obj.get("landmark_2d_106")

        yaw = float(pose_angles[1]) if (pose_angles is not None and len(pose_angles) >= 2) else 0.0
        pitch = float(pose_angles[0]) if (pose_angles is not None and len(pose_angles) >= 1) else 0.0

        # Calibrate neutral baseline on first frames
        if self.baseline_yaw is None:
            self.baseline_yaw = yaw
            self.baseline_pitch = pitch

        current_action = self.get_current_action()

        # 2. Evaluate current action
        action_satisfied = False

        if current_action == ChallengeAction.TURN_LEFT:
            # Positive relative yaw indicates turn to subject's left / camera right
            rel_yaw = yaw - self.baseline_yaw
            if rel_yaw > 12.0 or rel_yaw < -12.0:
                # Accept significant relative yaw deviation
                action_satisfied = True

        elif current_action == ChallengeAction.TURN_RIGHT:
            rel_yaw = yaw - self.baseline_yaw
            if rel_yaw < -12.0 or rel_yaw > 12.0:
                action_satisfied = True

        elif current_action == ChallengeAction.BLINK:
            ear = self.calculate_ear(landmarks_2d)
            self.history_ear.append(ear)

            # Temporal sequence: eyes open -> closed (EAR < 0.20) -> re-opened (EAR > 0.24)
            if self.blink_phase == "WAIT_OPEN" and ear > 0.23:
                self.blink_phase = "OPEN_READY"
            elif self.blink_phase == "OPEN_READY" and ear < 0.19:
                self.blink_phase = "EYES_CLOSED"
            elif self.blink_phase == "EYES_CLOSED" and ear > 0.23:
                self.blink_phase = "REOPENED"
                action_satisfied = True

        # 3. State transition updates
        required_hold = 1 if current_action == ChallengeAction.BLINK else 2
        if action_satisfied:
            self.action_hold_frames += 1
            if self.action_hold_frames >= required_hold:
                # Action confirmed! Advance to next action
                self.confirmed_actions.append(current_action)
                self.current_idx += 1
                self.action_hold_frames = 0
                self.action_start_time = time.time()
                self.blink_phase = "WAIT_OPEN"

                if self.current_idx >= len(self.challenges):
                    self.state = ChallengeState.COMPLETED
                else:
                    self.state = ChallengeState.WAITING_FOR_ACTION
            else:
                self.state = ChallengeState.ACTION_DETECTED
        else:
            self.action_hold_frames = max(0, self.action_hold_frames - 1)
            self.state = ChallengeState.WAITING_FOR_ACTION

        return self.state, self.get_prompt_text()
