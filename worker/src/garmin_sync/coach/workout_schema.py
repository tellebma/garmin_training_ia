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
    # Cadence : interprétation dépendante du sport, jamais validée numériquement
    # (pas de bornes physiologiques universelles) — rpm en vélo, foulées/min en
    # course, coups de bras/min en natation. Champ informatif transmis tel quel.
    cadence_low: int | None = None
    cadence_high: int | None = None


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
    "recovery": StructureCaps(5 * 60, 5 * 60, 0.80, 20 * 60),
    "endurance": StructureCaps(15 * 60, 10 * 60, 0.75, 30 * 60),
    "long": StructureCaps(15 * 60, 10 * 60, 0.80, 50 * 60),
    "threshold": StructureCaps(20 * 60, 15 * 60, 0.60, 40 * 60),
    "intervals": StructureCaps(25 * 60, 15 * 60, 0.50, 40 * 60),
}
_DEFAULT_CAPS = StructureCaps(20 * 60, 15 * 60, 0.55, 25 * 60)

# Part du budget warmup+cooldown allouée au warmup (le reste va au cooldown).
_WARMUP_BUDGET_SHARE = 0.6


def structure_caps_for_type(session_type: str) -> StructureCaps:
    return _CAPS_BY_TYPE.get(session_type, _DEFAULT_CAPS)


def duration_tolerance_s(target_duration_s: int) -> int:
    """Allowed deviation between generated total and the planned target."""
    return max(300, round(target_duration_s * 0.10))


@dataclass(frozen=True)
class SessionEnvelope:
    """Bornes effectives d'une séance, cohérentes entre prompt LLM et validation.

    Les caps warmup/cooldown sont dérivés du budget (1 - main_min_ratio) calculé
    sur la durée totale MINIMALE acceptée : un workout qui respecte ces caps et la
    fenêtre de durée satisfait mécaniquement le ratio de corps de séance.
    """

    session_type: str
    target_s: int
    tolerance_s: int
    floor_s: int
    warmup_max_s: int
    cooldown_max_s: int
    main_min_ratio: float


def envelope_for_session(session: dict[str, object]) -> SessionEnvelope:
    stype = str(session.get("session_type") or "endurance")
    caps = structure_caps_for_type(stype)
    target = session.get("target_duration_s")
    target_s = target if isinstance(target, int) and target > 0 else 0
    tol = duration_tolerance_s(target_s)
    min_total = max(caps.floor_s, target_s - tol)
    budget_s = int((1 - caps.main_min_ratio) * min_total)
    warmup_max = min(caps.warmup_max_s, int(budget_s * _WARMUP_BUDGET_SHARE))
    cooldown_max = min(caps.cooldown_max_s, budget_s - warmup_max)
    return SessionEnvelope(
        session_type=stype,
        target_s=target_s,
        tolerance_s=tol,
        floor_s=caps.floor_s,
        warmup_max_s=warmup_max,
        cooldown_max_s=cooldown_max,
        main_min_ratio=caps.main_min_ratio,
    )


def describe_session_envelope(session: dict[str, object]) -> str:
    """Human-readable numeric envelope the workout MUST satisfy, for the LLM prompt.

    Construit depuis `envelope_for_session`, la même source que
    `validate_workout_for_session` : le modèle voit exactement les bornes contre
    lesquelles il sera vérifié.
    """
    env = envelope_for_session(session)
    lo_min = -(-max(env.floor_s, env.target_s - env.tolerance_s) // 60)  # ceil, clampé au floor
    hi_min = (env.target_s + env.tolerance_s) // 60
    combined_min = (env.warmup_max_s + env.cooldown_max_s) // 60
    return (
        "Contraintes chiffrées à respecter impérativement (la séance sera rejetée sinon) :\n"
        f"- Durée totale entre {lo_min}min et {hi_min}min (cible {env.target_s // 60}min).\n"
        f"- Échauffement (warmup) ≤ {env.warmup_max_s // 60}min.\n"
        f"- Retour au calme (cooldown) ≤ {env.cooldown_max_s // 60}min.\n"
        f"- Échauffement + retour au calme ≤ {combined_min}min au total.\n"
        f"- Le corps de séance (main) doit représenter ≥ {env.main_min_ratio:.0%} "
        "de la durée totale."
    )


def validate_workout_for_session(workout: Workout, session: dict[str, object]) -> Workout:
    """Validate a generated workout against the planned session envelope."""
    target_duration = session.get("target_duration_s")
    if not isinstance(target_duration, int) or target_duration <= 0:
        raise ValueError("workout generation requires a positive target duration")

    env = envelope_for_session(session)
    total = workout.total_duration_s()

    if total < env.floor_s:
        raise ValueError(
            f"workout duration {total}s is too short for {env.session_type} (floor {env.floor_s}s)"
        )
    if workout.warmup.duration_s > env.warmup_max_s:
        raise ValueError(f"warmup {workout.warmup.duration_s}s exceeds cap {env.warmup_max_s}s")
    if workout.cooldown.duration_s > env.cooldown_max_s:
        raise ValueError(
            f"cooldown {workout.cooldown.duration_s}s exceeds cap {env.cooldown_max_s}s"
        )
    if workout.main_duration_s() / total < env.main_min_ratio:
        raise ValueError(f"main work below {env.main_min_ratio:.0%} for {env.session_type}")
    if abs(total - env.target_s) > env.tolerance_s:
        raise ValueError(f"workout duration {total}s is too far from target {env.target_s}s")
    return workout
