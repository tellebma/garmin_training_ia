"""Pydantic models for a single LLM-generated workout.

Matches the TypeScript Workout type in `lib/coach/workout-types.ts` —
when you change one, change the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Zone = Literal["Z1", "Z2", "Z3", "Z4", "Z5"]
Rpe = Annotated[int, Field(ge=1, le=10)]


class IntervalTarget(BaseModel):
    """Physiological target for an interval block."""

    label: Zone
    rpe: Rpe
    bpm_low: int | None = None
    bpm_high: int | None = None
    watts_low: int | None = None
    watts_high: int | None = None
    pace_low_kmh: float | None = None
    pace_high_kmh: float | None = None


class IntervalBlock(BaseModel):
    duration_s: int = Field(ge=1)
    target: IntervalTarget
    notes: str | None = None


class IntervalSet(BaseModel):
    """A repeated work/rest pattern (used for intervals/threshold sessions)."""

    reps: int = Field(ge=1, le=20)
    work: IntervalBlock
    rest: IntervalBlock


MainBlock = IntervalBlock | IntervalSet


def block_duration_s(block: MainBlock) -> int:
    """Total duration of one main block, including interval recoveries."""
    if isinstance(block, IntervalSet):
        return block.reps * (block.work.duration_s + block.rest.duration_s)
    return block.duration_s


class Workout(BaseModel):
    warmup: IntervalBlock
    main: list[MainBlock]
    cooldown: IntervalBlock
    summary_md: str
    technical_focus: str | None = None

    @model_validator(mode="after")
    def _check_non_empty(self) -> Workout:
        if not self.main:
            raise ValueError("workout must contain at least one main block")
        if self.total_duration_s() <= 0:
            raise ValueError("workout total duration must be positive")
        return self

    def total_duration_s(self) -> int:
        total = self.warmup.duration_s + self.cooldown.duration_s
        for block in self.main:
            total += block_duration_s(block)
        return total

    def main_duration_s(self) -> int:
        return sum(block_duration_s(block) for block in self.main)


@dataclass(frozen=True)
class StructureCaps:
    warmup_max_s: int
    cooldown_max_s: int
    main_min_ratio: float
    floor_s: int


_CAPS_BY_TYPE: dict[str, StructureCaps] = {
    "recovery": StructureCaps(5 * 60, 5 * 60, 0.90, 20 * 60),
    "endurance": StructureCaps(15 * 60, 10 * 60, 0.80, 30 * 60),
    "long": StructureCaps(15 * 60, 10 * 60, 0.80, 50 * 60),
    "threshold": StructureCaps(20 * 60, 15 * 60, 0.60, 40 * 60),
    "intervals": StructureCaps(25 * 60, 15 * 60, 0.50, 40 * 60),
}
_DEFAULT_CAPS = StructureCaps(20 * 60, 15 * 60, 0.55, 25 * 60)


def structure_caps_for_type(session_type: str) -> StructureCaps:
    return _CAPS_BY_TYPE.get(session_type, _DEFAULT_CAPS)


def duration_tolerance_s(target_duration_s: int) -> int:
    """Allowed deviation between generated total and the planned target."""
    return max(300, round(target_duration_s * 0.10))


def describe_session_envelope(session: dict[str, object]) -> str:
    """Human-readable numeric envelope the workout MUST satisfy, for the LLM prompt.

    Mirrors `validate_workout_for_session` so the model is told the exact bounds
    it will be checked against (the small model can't infer them otherwise).
    """
    stype = str(session.get("session_type") or "endurance")
    caps = structure_caps_for_type(stype)
    target = session.get("target_duration_s")
    target_s = target if isinstance(target, int) and target > 0 else 0
    tol = duration_tolerance_s(target_s)
    lo_min = max(0, (target_s - tol)) // 60
    hi_min = (target_s + tol) // 60
    return (
        "Contraintes chiffrées à respecter impérativement (la séance sera rejetée sinon) :\n"
        f"- Durée totale entre {lo_min}min et {hi_min}min (cible {target_s // 60}min).\n"
        f"- Échauffement (warmup) ≤ {caps.warmup_max_s // 60}min.\n"
        f"- Retour au calme (cooldown) ≤ {caps.cooldown_max_s // 60}min.\n"
        f"- Le corps de séance (main) doit représenter ≥ {caps.main_min_ratio:.0%} "
        "de la durée totale."
    )


def validate_workout_for_session(workout: Workout, session: dict[str, object]) -> Workout:
    """Validate a generated workout against the planned session envelope."""
    target_duration = session.get("target_duration_s")
    if not isinstance(target_duration, int) or target_duration <= 0:
        raise ValueError("workout generation requires a positive target duration")

    stype = str(session.get("session_type") or "endurance")
    caps = structure_caps_for_type(stype)
    total = workout.total_duration_s()

    if total < caps.floor_s:
        raise ValueError(
            f"workout duration {total}s is too short for {stype} (floor {caps.floor_s}s)"
        )
    if workout.warmup.duration_s > caps.warmup_max_s:
        raise ValueError(f"warmup {workout.warmup.duration_s}s exceeds cap {caps.warmup_max_s}s")
    if workout.cooldown.duration_s > caps.cooldown_max_s:
        raise ValueError(
            f"cooldown {workout.cooldown.duration_s}s exceeds cap {caps.cooldown_max_s}s"
        )
    if workout.main_duration_s() / total < caps.main_min_ratio:
        raise ValueError(f"main work below {caps.main_min_ratio:.0%} for {stype}")

    tolerance_s = duration_tolerance_s(target_duration)
    if abs(total - target_duration) > tolerance_s:
        raise ValueError(f"workout duration {total}s is too far from target {target_duration}s")
    return workout
