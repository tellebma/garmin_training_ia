"""Pydantic models for a single LLM-generated workout.

Matches the TypeScript Workout type in `lib/coach/workout-types.ts` —
when you change one, change the other.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

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


class Workout(BaseModel):
    warmup: IntervalBlock
    main: list[MainBlock]
    cooldown: IntervalBlock
    summary_md: str
    technical_focus: str | None = None

    def total_duration_s(self) -> int:
        total = self.warmup.duration_s + self.cooldown.duration_s
        for block in self.main:
            if isinstance(block, IntervalSet):
                total += block.reps * (block.work.duration_s + block.rest.duration_s)
            else:
                total += block.duration_s
        return total
