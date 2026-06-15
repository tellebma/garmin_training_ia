"""Pydantic models for a single LLM-generated workout.

Matches the TypeScript Workout type in `lib/coach/workout-types.ts` —
when you change one, change the other.
"""

from __future__ import annotations

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
    def _check_realistic_structure(self) -> Workout:
        if not self.main:
            raise ValueError("workout must contain at least one main block")
        total = self.total_duration_s()
        if total <= 0:
            raise ValueError("workout total duration must be positive")
        if self.main_duration_s() / total < 0.55:
            raise ValueError("main work must represent at least 55% of workout duration")
        return self

    def total_duration_s(self) -> int:
        total = self.warmup.duration_s + self.cooldown.duration_s
        for block in self.main:
            total += block_duration_s(block)
        return total

    def main_duration_s(self) -> int:
        return sum(block_duration_s(block) for block in self.main)


def validate_workout_for_session(workout: Workout, session: dict[str, object]) -> Workout:
    """Validate a generated workout against the planned session envelope."""
    target_duration = session.get("target_duration_s")
    if not isinstance(target_duration, int) or target_duration <= 0:
        raise ValueError("workout generation requires a positive target duration")

    total = workout.total_duration_s()
    tolerance_s = max(300, round(target_duration * 0.10))
    if abs(total - target_duration) > tolerance_s:
        raise ValueError(f"workout duration {total}s is too far from target {target_duration}s")
    return workout
