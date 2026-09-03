"""Read-only deterministic trajectory classification from progression evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


CLASSIFIER_VERSION = "training-trajectory-v1"
MINIMUM_COMPARABLE_OBSERVATIONS = 3
FORWARD_DECISIONS = frozenset({"increase_load", "increase_repetitions", "increase_sets"})


@dataclass(frozen=True)
class TrajectoryObservation:
    completion_id: str
    progression_event_id: str
    plan_id: str
    plan_version: str
    prescription_id: str
    exercise_id: str
    exercise_version: str
    occurred_at: datetime
    decision_type: str


@dataclass(frozen=True)
class TrainingTrajectory:
    classifier_version: str
    state: str
    exercise_id: str | None
    exercise_version: str | None
    completion_ids: tuple[str, ...] = ()
    progression_event_ids: tuple[str, ...] = ()


def classify(observations: tuple[TrajectoryObservation, ...]) -> TrainingTrajectory:
    """Classify only exact, repeated authoritative progression observations."""
    if not isinstance(observations, tuple) or not observations:
        return TrainingTrajectory(CLASSIFIER_VERSION, "insufficient_evidence", None, None)
    if any(not isinstance(item, TrajectoryObservation) or item.occurred_at.tzinfo is None for item in observations):
        return TrainingTrajectory(CLASSIFIER_VERSION, "insufficient_evidence", None, None)
    identities = {(item.plan_id, item.plan_version, item.exercise_id, item.exercise_version)
                  for item in observations}
    if len(identities) != 1:
        return TrainingTrajectory(CLASSIFIER_VERSION, "insufficient_evidence", None, None)
    ordered = tuple(sorted(observations, key=lambda item: (item.occurred_at, item.completion_id)))
    if len({item.completion_id for item in ordered}) != len(ordered):
        return TrainingTrajectory(CLASSIFIER_VERSION, "insufficient_evidence", None, None)
    exemplar = ordered[-1]
    completion_ids = tuple(item.completion_id for item in ordered)
    event_ids = tuple(item.progression_event_id for item in ordered)
    if len(ordered) < MINIMUM_COMPARABLE_OBSERVATIONS:
        return TrainingTrajectory(CLASSIFIER_VERSION, "insufficient_evidence", exemplar.exercise_id,
                                  exemplar.exercise_version, completion_ids, event_ids)
    if any(item.decision_type in FORWARD_DECISIONS for item in ordered):
        return TrainingTrajectory(CLASSIFIER_VERSION, "progressing", exemplar.exercise_id,
                                  exemplar.exercise_version, completion_ids, event_ids)
    if all(item.decision_type == "maintain" for item in ordered):
        return TrainingTrajectory(CLASSIFIER_VERSION, "stable", exemplar.exercise_id,
                                  exemplar.exercise_version, completion_ids, event_ids)
    # No existing authority defines regression or stall from these facts.
    return TrainingTrajectory(CLASSIFIER_VERSION, "insufficient_evidence", exemplar.exercise_id,
                              exemplar.exercise_version, completion_ids, event_ids)
