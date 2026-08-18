"""
Classroom Multi-Face Tracker and Burst Decision Aggregator Module.
Implements track-level temporal evidence accumulation across the burst window:
- Spatial-temporal face tracking across sample frames (Centroid + IoU association)
- Multi-observation evidence collection per tracked student (embeddings, PAD scores, quality tiers)
- Window-level candidate identity voting & final aggregated decision engine
- Single attendance decision committed exactly ONCE per window.
"""

import time
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

from config import (
    MATCH_THRESHOLD,
    PAD_SCORE_THRESHOLD,
    BURST_MIN_VALID_OBSERVATIONS,
    BURST_IDENTITY_SUPPORT_RATIO,
    BURST_TRACK_MAX_ABSENT_FRAMES
)
from .quality import QualityTier, QualityResult
from .pad_engine import PADResult


@dataclass
class FaceObservation:
    """Individual frame observation for a tracked face."""
    timestamp: float
    bbox: np.ndarray
    quality_res: QualityResult
    pad_res: Optional[PADResult] = None
    embedding: Optional[np.ndarray] = None
    matched_id: Optional[str] = None
    matched_name: Optional[str] = None
    similarity: float = 0.0
    crop_image: Optional[np.ndarray] = None


@dataclass
class TrackEvidence:
    """Accumulated biometric & liveness evidence for a single tracked person across the burst."""
    track_id: int
    first_seen: float
    last_seen: float
    last_bbox: np.ndarray
    absent_frames: int = 0
    observations: List[FaceObservation] = field(default_factory=list)
    best_crop: Optional[np.ndarray] = None
    best_sharpness: float = 0.0

    def add_observation(self, obs: FaceObservation):
        self.observations.append(obs)
        self.last_seen = obs.timestamp
        self.last_bbox = obs.bbox
        self.absent_frames = 0

        # Retain cleanest crop for archiving if needed
        if obs.quality_res.blur_score > self.best_sharpness and obs.crop_image is not None:
            self.best_sharpness = obs.quality_res.blur_score
            self.best_crop = obs.crop_image


@dataclass
class TrackDecision:
    """Final aggregated decision for a tracked face across the burst window."""
    track_id: int
    status: str  # "PRESENT", "UNRESOLVED", "UNKNOWN"
    identity: Optional[str] = None
    student_name: Optional[str] = None
    median_similarity: float = 0.0
    top_similarity: float = 0.0
    support_ratio: float = 0.0
    valid_observations_count: int = 0
    total_observations_count: int = 0
    pad_score: float = 0.0
    pad_passed: bool = False
    best_crop: Optional[np.ndarray] = None
    reason: str = ""


class ClassroomFaceTracker:
    """
    Lightweight Centroid + IoU multi-face spatial-temporal tracker for classroom video.
    Maintains continuous track identities across sample frames.
    """

    def __init__(self, iou_threshold: float = 0.30, max_centroid_dist: float = 120.0):
        self.iou_threshold = iou_threshold
        self.max_centroid_dist = max_centroid_dist
        self.next_track_id = 1
        self.active_tracks: Dict[int, TrackEvidence] = {}
        self.closed_tracks: List[TrackEvidence] = []

    @staticmethod
    def _compute_iou(boxA: np.ndarray, boxB: np.ndarray) -> float:
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = max(1e-5, (boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
        boxBArea = max(1e-5, (boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))

        return interArea / float(boxAArea + boxBArea - interArea)

    @staticmethod
    def _compute_centroid_dist(boxA: np.ndarray, boxB: np.ndarray) -> float:
        cAx, cAy = (boxA[0] + boxA[2]) / 2.0, (boxA[1] + boxA[3]) / 2.0
        cBx, cBy = (boxB[0] + boxB[2]) / 2.0, (boxB[1] + boxB[3]) / 2.0
        return math.hypot(cAx - cBx, cAy - cBy)

    def update(self, current_observations: List[FaceObservation]) -> List[Tuple[int, FaceObservation]]:
        """
        Associates current frame face detections with existing tracks or creates new ones.
        Returns list of (track_id, observation).
        """
        now = time.time()
        matched_results = []
        unmatched_observations = list(range(len(current_observations)))
        active_ids = list(self.active_tracks.keys())

        # Build cost matrix
        if active_ids and current_observations:
            matches = []
            for t_idx, track_id in enumerate(active_ids):
                track = self.active_tracks[track_id]
                for o_idx in unmatched_observations:
                    obs = current_observations[o_idx]
                    iou = self._compute_iou(track.last_bbox, obs.bbox)
                    dist = self._compute_centroid_dist(track.last_bbox, obs.bbox)
                    if iou >= self.iou_threshold or dist <= self.max_centroid_dist:
                        # Prioritize higher IoU and closer centroid distance
                        score = iou * 100.0 - dist
                        matches.append((score, track_id, o_idx))

            # Sort best matches first
            matches.sort(key=lambda x: x[0], reverse=True)
            assigned_tracks = set()
            assigned_obs = set()

            for _, track_id, o_idx in matches:
                if track_id not in assigned_tracks and o_idx not in assigned_obs:
                    assigned_tracks.add(track_id)
                    assigned_obs.add(o_idx)
                    self.active_tracks[track_id].add_observation(current_observations[o_idx])
                    matched_results.append((track_id, current_observations[o_idx]))

            unmatched_observations = [i for i in unmatched_observations if i not in assigned_obs]
            for track_id in active_ids:
                if track_id not in assigned_tracks:
                    self.active_tracks[track_id].absent_frames += 1

        # Create new tracks for unmatched observations
        for o_idx in unmatched_observations:
            obs = current_observations[o_idx]
            new_id = self.next_track_id
            self.next_track_id += 1
            track = TrackEvidence(
                track_id=new_id,
                first_seen=obs.timestamp,
                last_seen=obs.timestamp,
                last_bbox=obs.bbox
            )
            track.add_observation(obs)
            self.active_tracks[new_id] = track
            matched_results.append((new_id, obs))

        # Close dead tracks that disappeared for too many frames
        dead_ids = [tid for tid, trk in self.active_tracks.items() if trk.absent_frames > BURST_TRACK_MAX_ABSENT_FRAMES]
        for tid in dead_ids:
            self.closed_tracks.append(self.active_tracks.pop(tid))

        return matched_results

    def get_all_tracks(self) -> List[TrackEvidence]:
        """Returns all completed and active tracks across the entire burst window."""
        return list(self.active_tracks.values()) + self.closed_tracks


class BurstDecisionAggregator:
    """
    Evaluates accumulated track evidence over the entire burst window and produces
    window-level attendance decisions. Enforces fail-closed rules and candidate voting.
    """

    @staticmethod
    def aggregate_track(
        track: TrackEvidence,
        min_valid_obs: int = BURST_MIN_VALID_OBSERVATIONS,
        support_ratio_thresh: float = BURST_IDENTITY_SUPPORT_RATIO,
        match_thresh: float = MATCH_THRESHOLD,
        pad_thresh: float = PAD_SCORE_THRESHOLD
    ) -> TrackDecision:
        """
        Aggregates per-observation evidence for a single track into an atomic TrackDecision.
        """
        total_obs = len(track.observations)
        if total_obs == 0:
            return TrackDecision(
                track_id=track.track_id,
                status="UNRESOLVED",
                reason="No observations recorded"
            )

        # Filter observations by quality
        safe_obs = [o for o in track.observations if o.quality_res.tier == QualityTier.RECOGNITION_SAFE and o.embedding is not None]
        trackable_obs = [o for o in track.observations if o.quality_res.tier == QualityTier.TRACKABLE_BUT_SMALL]

        # 1. Check if track was only small/distant throughout with no safe recognition frames
        if len(safe_obs) == 0:
            return TrackDecision(
                track_id=track.track_id,
                status="UNRESOLVED",
                total_observations_count=total_obs,
                best_crop=track.best_crop,
                reason="Face observed but too small/distant throughout burst for safe biometric identification"
            )

        # 2. Multi-frame PAD Aggregation
        pad_scores = [o.pad_res.score for o in safe_obs if o.pad_res is not None]
        if not pad_scores:
            pad_scores = [o.pad_res.score for o in track.observations if o.pad_res is not None]

        median_pad = float(np.median(pad_scores)) if pad_scores else 0.0
        pad_passed = (median_pad >= pad_thresh) and (len(pad_scores) >= 1)

        if not pad_passed:
            return TrackDecision(
                track_id=track.track_id,
                status="UNRESOLVED",
                pad_score=median_pad,
                pad_passed=False,
                valid_observations_count=len(safe_obs),
                total_observations_count=total_obs,
                best_crop=track.best_crop,
                reason=f"Multi-frame Anti-Spoofing Check Failed (Median PAD: {median_pad:.2f} < {pad_thresh:.2f})"
            )

        # 3. Candidate Identity Voting
        # Group observations by matched student_id
        identity_votes: Dict[str, List[FaceObservation]] = {}
        for o in safe_obs:
            if o.matched_id:
                identity_votes.setdefault(o.matched_id, []).append(o)

        if not identity_votes:
            # High quality face but unrecognized against all enrolled templates
            scores = [o.similarity for o in safe_obs]
            top_score = max(scores) if scores else 0.0
            return TrackDecision(
                track_id=track.track_id,
                status="UNKNOWN",
                median_similarity=float(np.median(scores)) if scores else 0.0,
                top_similarity=top_score,
                pad_score=median_pad,
                pad_passed=True,
                valid_observations_count=len(safe_obs),
                total_observations_count=total_obs,
                best_crop=track.best_crop,
                reason=f"Unrecognized student face across burst (Top similarity: {top_score:.2f} < {match_thresh:.2f})"
            )

        # Find candidate identity with highest number of matching observations
        top_candidate_id, top_candidate_obs = max(identity_votes.items(), key=lambda item: len(item[1]))
        candidate_sims = [o.similarity for o in top_candidate_obs]
        top_name = top_candidate_obs[0].matched_name or "Student"

        median_sim = float(np.median(candidate_sims))
        top_sim = float(max(candidate_sims))
        support_ratio = len(top_candidate_obs) / float(len(safe_obs))

        # 4. Check for sufficient observations & candidate consistency
        if len(top_candidate_obs) < min_valid_obs:
            return TrackDecision(
                track_id=track.track_id,
                status="UNRESOLVED",
                identity=top_candidate_id,
                student_name=top_name,
                median_similarity=median_sim,
                top_similarity=top_sim,
                support_ratio=support_ratio,
                pad_score=median_pad,
                pad_passed=True,
                valid_observations_count=len(top_candidate_obs),
                total_observations_count=total_obs,
                best_crop=track.best_crop,
                reason=f"Insufficient matching observations ({len(top_candidate_obs)} < {min_valid_obs} required)"
            )

        if support_ratio < support_ratio_thresh:
            return TrackDecision(
                track_id=track.track_id,
                status="UNRESOLVED",
                identity=top_candidate_id,
                student_name=top_name,
                median_similarity=median_sim,
                top_similarity=top_sim,
                support_ratio=support_ratio,
                pad_score=median_pad,
                pad_passed=True,
                valid_observations_count=len(top_candidate_obs),
                total_observations_count=total_obs,
                best_crop=track.best_crop,
                reason=f"Conflicting identity evidence across burst (Support: {support_ratio*100:.1f}% < {support_ratio_thresh*100:.1f}%)"
            )

        if median_sim < match_thresh:
            return TrackDecision(
                track_id=track.track_id,
                status="UNRESOLVED",
                identity=top_candidate_id,
                student_name=top_name,
                median_similarity=median_sim,
                top_similarity=top_sim,
                support_ratio=support_ratio,
                pad_score=median_pad,
                pad_passed=True,
                valid_observations_count=len(top_candidate_obs),
                total_observations_count=total_obs,
                best_crop=track.best_crop,
                reason=f"Median similarity below match threshold ({median_sim:.2f} < {match_thresh:.2f})"
            )

        # 5. All gates passed -> PRESENT
        return TrackDecision(
            track_id=track.track_id,
            status="PRESENT",
            identity=top_candidate_id,
            student_name=top_name,
            median_similarity=median_sim,
            top_similarity=top_sim,
            support_ratio=support_ratio,
            valid_observations_count=len(top_candidate_obs),
            total_observations_count=total_obs,
            pad_score=median_pad,
            pad_passed=True,
            best_crop=track.best_crop,
            reason=f"Verified PRESENT with {len(top_candidate_obs)} consistent observations (Median: {median_sim:.2f}, PAD: {median_pad:.2f})"
        )

    @classmethod
    def evaluate_burst_window(
        cls,
        all_tracks: List[TrackEvidence],
        enrolled_student_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Aggregates all tracks from the burst window and maps them to enrolled students.
        Returns final window attendance map {student_id: (status, confidence, reason)}
        and list of deduplicated unknown face crops.
        """
        student_results: Dict[str, TrackDecision] = {}
        unknown_tracks: List[TrackDecision] = []
        unresolved_tracks: List[TrackDecision] = []

        for track in all_tracks:
            decision = cls.aggregate_track(track)
            if decision.status == "PRESENT" and decision.identity:
                # If same student was tracked under multiple tracks, take highest median confidence
                if decision.identity not in student_results or decision.median_similarity > student_results[decision.identity].median_similarity:
                    student_results[decision.identity] = decision
            elif decision.status == "UNKNOWN":
                unknown_tracks.append(decision)
            else:
                unresolved_tracks.append(decision)

        # Build final outcome for all enrolled students
        final_records = []
        for sid in enrolled_student_ids:
            if sid in student_results:
                dec = student_results[sid]
                final_records.append({
                    "student_id": sid,
                    "student_name": dec.student_name,
                    "status": "PRESENT",
                    "confidence": dec.median_similarity,
                    "pad_score": dec.pad_score,
                    "valid_obs": dec.valid_observations_count,
                    "reason": dec.reason
                })
            else:
                # Check if any unresolved track belonged to this student
                matching_unresolved = [u for u in unresolved_tracks if u.identity == sid]
                if matching_unresolved:
                    u_dec = matching_unresolved[0]
                    final_records.append({
                        "student_id": sid,
                        "student_name": u_dec.student_name,
                        "status": "UNRESOLVED",
                        "confidence": u_dec.median_similarity,
                        "pad_score": u_dec.pad_score,
                        "valid_obs": u_dec.valid_observations_count,
                        "reason": u_dec.reason
                    })
                else:
                    final_records.append({
                        "student_id": sid,
                        "student_name": None,
                        "status": "ABSENT",
                        "confidence": 0.0,
                        "pad_score": 0.0,
                        "valid_obs": 0,
                        "reason": "Not observed during burst window"
                    })

        return {
            "records": final_records,
            "present_count": len(student_results),
            "unknown_tracks": unknown_tracks,
            "unresolved_tracks": unresolved_tracks
        }
