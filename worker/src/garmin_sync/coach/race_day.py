"""Contenu du jour de course, dérivé des ``legs`` du race_goal (issue #157).

Le jour J était une case vide : ni durée estimée, ni TSS, ni déroulé — l'athlète
n'avait ni objectif de temps, ni pacing par segment, ni plan nutrition, ni
consigne de transition, et la charge du jour J comptait pour zéro dans le bilan.

Tout est calculé de façon DÉTERMINISTE (pas de LLM) : le jour de course est une
projection arithmétique de données déjà saisies (distances, D+, allures de
référence, niveau par discipline, marqueurs de performance). Un modèle n'y
apporterait qu'un risque d'allure hallucinée, un coût par régénération et une
sortie non reproductible — là où l'athlète a besoin d'un temps de passage stable
sur lequel construire sa course.

Les vitesses de référence sont partagées avec ``planner.estimate_race_time_shares``
(source unique) : le temps estimé du jour J et la répartition des séances de
préparation racontent la même course.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from garmin_sync.coach.workout_schema import (
    IntervalBlock,
    IntervalTarget,
    MainBlock,
    Workout,
    Zone,
    enrich_block_targets,
)

# Vitesses de croisière amateur (km/h) et pénalité de grimpe (~20 min / 1000 m).
RACE_SPEED_KMH: dict[str, float] = {"swim": 3.2, "bike": 25.0, "run": 10.0, "brick": 12.0}
RACE_SPEED_DEFAULT_KMH = 12.0
CLIMB_HOURS_PER_1000M = 0.33

# Niveau par discipline (1-5) -> facteur appliqué à la vitesse de référence.
_LEVEL_SPEED_FACTOR: dict[int, float] = {1: 0.85, 2: 0.92, 3: 1.00, 4: 1.08, 5: 1.15}
_DEFAULT_LEVEL = 3

# Part de VMA tenable sur la partie course à pied d'une épreuve d'endurance.
_RUN_RACE_PCT_VMA = 0.72
# En eau libre (combinaison, navigation, pack) l'allure reste proche du CSS.
_SWIM_RACE_CSS_FACTOR = 1.03

_DISCIPLINE_LABEL: dict[str, str] = {
    "swim": "Natation",
    "bike": "Vélo",
    "run": "Course à pied",
    "brick": "Enchaînement",
}

# Transitions : durées d'aire de transition observées en amateur.
_TRANSITION_S: dict[tuple[str, str], int] = {("swim", "bike"): 300, ("bike", "run"): 180}
_TRANSITION_DEFAULT_S = 180
_TRANSITION_NAME: dict[tuple[str, str], str] = {("swim", "bike"): "T1", ("bike", "run"): "T2"}
# Une transition n'est ni du vélo ni de la course : lui donner la discipline
# suivante lui collerait une puissance ou une allure de course, absurde à pied
# nu dans une aire de transition. Discipline neutre -> seule la FC est enrichie.
_TRANSITION_SPORT = "transition"

_COOLDOWN_S = 600
_WARMUP_SHORT_RACE_S = 1500  # course < 3 h : échauffement complet
_WARMUP_LONG_RACE_S = 900  # course longue : l'échauffement se fait dans la course
_LONG_RACE_S = 3 * 3600

# Facteur d'intensité de l'échauffement + retour au calme, pour que leur charge
# ne disparaisse pas du TSS du jour (≈ 30 TSS/h).
_PREP_INTENSITY_FACTOR = 0.55


@dataclass(frozen=True)
class RaceSegment:
    """Un segment de course exploitable, avec son temps estimé."""

    discipline: str
    distance_km: float
    elevation_gain_m: int
    duration_s: int


@dataclass(frozen=True)
class RaceIntensity:
    """Intensité tenable sur la course, fonction de sa durée totale."""

    zone: Zone
    rpe: int
    intensity_factor: float


# Plus la course est longue, plus l'intensité soutenable baisse.
_INTENSITY_TIERS: tuple[tuple[int, RaceIntensity], ...] = (
    (3600, RaceIntensity("Z4", 8, 0.92)),
    (3 * 3600, RaceIntensity("Z4", 7, 0.85)),
    (6 * 3600, RaceIntensity("Z3", 6, 0.78)),
)
_INTENSITY_ULTRA = RaceIntensity("Z2", 5, 0.70)


@dataclass(frozen=True)
class Fueling:
    """Consignes de ravitaillement proportionnées à la durée de l'épreuve."""

    fluid: str
    carbs: str
    sodium: str | None
    headline: str


_FUELING_TIERS: tuple[tuple[int, Fueling], ...] = (
    (
        90 * 60,
        Fueling(
            fluid="400-600 ml/h",
            carbs="0-30 g",
            sodium=None,
            headline="Épreuve courte : l'eau suffit, un gel 15 min avant le départ si besoin.",
        ),
    ),
    (
        3 * 3600,
        Fueling(
            fluid="500-750 ml/h",
            carbs="30-45 g",
            sodium=None,
            headline="Ravitaillement léger mais régulier, dès la 30e minute.",
        ),
    ),
    (
        6 * 3600,
        Fueling(
            fluid="600-800 ml/h",
            carbs="60-80 g",
            sodium="300-500 mg",
            headline="Manger tôt et souvent : l'essentiel des calories se prend sur le vélo.",
        ),
    ),
)
_FUELING_ULTRA = Fueling(
    fluid="700-900 ml/h",
    carbs="60-90 g",
    sodium="500-700 mg",
    headline="Alterner solide et liquide, jamais plus de 30 min sans apport.",
)


def _positive(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _level_factor(discipline: str, athlete: dict[str, Any]) -> float:
    strengths = athlete.get("sports_strengths") or {}
    score = strengths.get(discipline) if isinstance(strengths, dict) else None
    if not isinstance(score, int) or isinstance(score, bool):
        score = _DEFAULT_LEVEL
    return _LEVEL_SPEED_FACTOR.get(min(5, max(1, score)), 1.0)


def race_speed_kmh(discipline: str, athlete: dict[str, Any]) -> float:
    """Vitesse de course estimée sur une discipline.

    Les marqueurs de performance mesurés (VMA, CSS) priment sur les vitesses de
    référence : ils portent déjà le niveau de l'athlète, donc le facteur de
    niveau déclaré ne s'y applique pas (il ferait double emploi). Le vélo reste
    sur la référence, faute de capteur de puissance exploitable pour en dériver
    une vitesse fiable (le rapport puissance/vitesse dépend du parcours).
    """
    if discipline == "run":
        vma = _positive(athlete.get("vma_kmh"))
        if vma:
            return vma * _RUN_RACE_PCT_VMA
    if discipline == "swim":
        css = _positive(athlete.get("css_per_100m_s"))
        if css:
            return 3600 / (css * _SWIM_RACE_CSS_FACTOR * 10)
    base = RACE_SPEED_KMH.get(discipline, RACE_SPEED_DEFAULT_KMH)
    return base * _level_factor(discipline, athlete)


def estimate_race_segments(
    legs: list[dict[str, Any]] | None, *, athlete: dict[str, Any] | None
) -> list[RaceSegment]:
    """Segments exploitables de la course, dans l'ordre de saisie.

    Un leg sans distance utilisable ne produit aucun temps : il est écarté
    plutôt que rendu comme un bloc de durée nulle (que le schéma refuserait).
    """
    profile = athlete or {}
    segments: list[RaceSegment] = []
    for leg in legs or []:
        discipline = str(leg.get("discipline") or "unknown")
        distance_km = _positive(leg.get("distance_km"))
        if distance_km is None:
            continue
        dplus = int(_positive(leg.get("elevation_gain_m")) or 0)
        hours = distance_km / race_speed_kmh(discipline, profile)
        hours += dplus / 1000 * CLIMB_HOURS_PER_1000M
        segments.append(
            RaceSegment(
                discipline=discipline,
                distance_km=distance_km,
                elevation_gain_m=dplus,
                duration_s=round(hours * 3600),
            )
        )
    return [s for s in segments if s.duration_s > 0]


def _intensity_for(moving_s: int) -> RaceIntensity:
    for limit, intensity in _INTENSITY_TIERS:
        if moving_s < limit:
            return intensity
    return _INTENSITY_ULTRA


def _fueling_for(moving_s: int) -> Fueling:
    for limit, fueling in _FUELING_TIERS:
        if moving_s < limit:
            return fueling
    return _FUELING_ULTRA


def _transition_between(previous: str, following: str) -> tuple[str, int]:
    key = (previous, following)
    name = _TRANSITION_NAME.get(key, "Transition")
    return name, _TRANSITION_S.get(key, _TRANSITION_DEFAULT_S)


def format_duration(seconds: int) -> str:
    """« 2h32 » / « 47min » — lisible dans une note de séance."""
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes}min"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h" if rest == 0 else f"{hours}h{rest:02d}"


def _label(discipline: str) -> str:
    return _DISCIPLINE_LABEL.get(discipline, discipline.capitalize())


def _km(distance_km: float) -> str:
    """« 1,4 km » — décimale française, sans zéro inutile."""
    return f"{distance_km:g} km".replace(".", ",")


def _segment_target(
    segment: RaceSegment, intensity: RaceIntensity, athlete: dict[str, Any]
) -> IntervalTarget:
    """Cible du segment : allures dérivées du temps estimé, pas de la table de zones.

    Une allure de zone (% VMA, % FTP) contredirait le chrono affiché juste
    au-dessus ; on publie donc la fourchette effectivement projetée (±3 %) et on
    laisse l'enrichissement générique ne combler que la FC.
    """
    target = IntervalTarget(label=intensity.zone, rpe=intensity.rpe)
    speed = segment.distance_km / (segment.duration_s / 3600)
    if segment.discipline == "run":
        return target.model_copy(
            update={
                "pace_low_kmh": round(speed * 0.97, 1),
                "pace_high_kmh": round(speed * 1.03, 1),
            }
        )
    if segment.discipline == "swim":
        per_100m = 360 / speed
        return target.model_copy(
            update={
                "pace_per_100m_low_s": max(1, round(per_100m * 0.97)),
                "pace_per_100m_high_s": max(1, round(per_100m * 1.03)),
            }
        )
    ftp = _positive(athlete.get("ftp_watts")) if segment.discipline == "bike" else None
    if ftp:
        race_watts = ftp * intensity.intensity_factor
        return target.model_copy(
            update={
                "watts_low": round(race_watts * 0.95),
                "watts_high": round(race_watts * 1.05),
            }
        )
    return target


def _segment_note(
    segment: RaceSegment, intensity: RaceIntensity, fueling: Fueling, position: int
) -> str:
    parts = [
        f"{_label(segment.discipline)} — {_km(segment.distance_km)}",
    ]
    if segment.elevation_gain_m:
        parts.append(f"{segment.elevation_gain_m} m D+")
    parts.append(f"objectif {format_duration(segment.duration_s)}")
    parts.append(f"{intensity.zone} / RPE {intensity.rpe}")
    parts.append(_pacing_advice(segment, position))
    if segment.discipline != "swim":
        parts.append(f"boire {fueling.fluid}, {fueling.carbs} de glucides/h")
    return " · ".join(parts)


def _pacing_advice(segment: RaceSegment, position: int) -> str:
    if position == 0:
        return "pars volontairement en dessous de ta sensation, le chrono se joue plus tard"
    if segment.elevation_gain_m >= 500:
        return "monte en régularité, ne jamais partir en sur-régime dans une bosse"
    return "tiens l'allure sans jamais accélérer par à-coups"


def _warmup_block(first: RaceSegment, moving_s: int, athlete: dict[str, Any]) -> IntervalBlock:
    duration = _WARMUP_LONG_RACE_S if moving_s >= _LONG_RACE_S else _WARMUP_SHORT_RACE_S
    block = IntervalBlock(
        duration_s=duration,
        target=IntervalTarget(label="Z1", rpe=3),
        notes=(
            "Échauffement d'avant-course : mobilité, 10 min très souple, "
            f"puis 3 à 4 accélérations progressives en {_label(first.discipline).lower()}. "
            "Dernière gorgée d'eau 15 min avant le départ."
        ),
    )
    return enrich_block_targets(block, athlete=athlete, sport=first.discipline)


def _cooldown_block(last: RaceSegment, athlete: dict[str, Any]) -> IntervalBlock:
    block = IntervalBlock(
        duration_s=_COOLDOWN_S,
        target=IntervalTarget(label="Z1", rpe=2),
        notes=(
            "Retour au calme : 10 min très souple, boire immédiatement, "
            "puis 20 à 30 g de protéines dans l'heure."
        ),
    )
    return enrich_block_targets(block, athlete=athlete, sport=last.discipline)


def _main_blocks(
    segments: list[RaceSegment],
    intensity: RaceIntensity,
    fueling: Fueling,
    athlete: dict[str, Any],
) -> list[MainBlock]:
    blocks: list[MainBlock] = []
    for position, segment in enumerate(segments):
        if position > 0:
            previous = segments[position - 1].discipline
            if previous != segment.discipline:
                blocks.append(_transition_block(previous, segment.discipline, athlete))
        block = IntervalBlock(
            duration_s=segment.duration_s,
            distance_m=max(1, round(segment.distance_km * 1000)),
            target=_segment_target(segment, intensity, athlete),
            notes=_segment_note(segment, intensity, fueling, position),
        )
        blocks.append(enrich_block_targets(block, athlete=athlete, sport=segment.discipline))
    return blocks


def _transition_block(previous: str, following: str, athlete: dict[str, Any]) -> IntervalBlock:
    name, duration = _transition_between(previous, following)
    block = IntervalBlock(
        duration_s=duration,
        target=IntervalTarget(label="Z2", rpe=4),
        notes=(
            f"{name} ({_label(previous).lower()} → {_label(following).lower()}) — "
            f"objectif {format_duration(duration)} : "
            "matériel posé dans l'ordre d'utilisation, marche puis course dans l'aire, "
            "et bois dès la sortie."
        ),
    )
    return enrich_block_targets(block, athlete=athlete, sport=_TRANSITION_SPORT)


def _summary(
    segments: list[RaceSegment], moving_s: int, intensity: RaceIntensity, fueling: Fueling
) -> str:
    splits = " + ".join(
        f"{_label(s.discipline).lower()} {format_duration(s.duration_s)}" for s in segments
    )
    transitions = sum(
        _transition_between(segments[i - 1].discipline, s.discipline)[1]
        for i, s in enumerate(segments)
        if i > 0 and segments[i - 1].discipline != s.discipline
    )
    lines = [
        f"Objectif de temps : {format_duration(moving_s)} ({splits}"
        + (f" + {format_duration(transitions)} de transitions" if transitions else "")
        + ").",
        f"Allure cible : {intensity.zone}, RPE {intensity.rpe} — "
        "les 20 premières minutes de chaque segment doivent sembler trop faciles.",
        f"Hydratation et nutrition : boire {fueling.fluid}, {fueling.carbs} de glucides/h"
        + (f", {fueling.sodium} de sodium/h" if fueling.sodium else "")
        + f". {fueling.headline}",
    ]
    if transitions:
        lines.append(
            "Transitions : repérer l'emplacement au réveil, poser le matériel dans l'ordre "
            "d'utilisation, et compter chaque transition dans le temps total."
        )
    return "\n".join(lines)


def _empty_race_day(*, day: date, race_sport: str, week_offset: int) -> dict[str, Any]:
    """Jour J sans legs exploitables : la case reste vide, mais reste valide."""
    return {
        "date": day.isoformat(),
        "sport": race_sport,
        "session_type": "race",
        "target_duration_s": None,
        "target_tss": None,
        "target_elevation_gain_m": None,
        "phase": "race",
        "week_offset": week_offset,
    }


def build_race_day_session(
    *,
    day: date,
    race_sport: str,
    week_offset: int,
    legs: list[dict[str, Any]] | None,
    athlete: dict[str, Any] | None,
) -> dict[str, Any]:
    """Séance du jour de course : durée estimée, TSS, et déroulé segment par segment."""
    profile = athlete or {}
    segments = estimate_race_segments(legs, athlete=profile)
    if not segments:
        return _empty_race_day(day=day, race_sport=race_sport, week_offset=week_offset)

    moving_s = sum(s.duration_s for s in segments) + sum(
        _transition_between(segments[i - 1].discipline, s.discipline)[1]
        for i, s in enumerate(segments)
        if i > 0 and segments[i - 1].discipline != s.discipline
    )
    intensity = _intensity_for(moving_s)
    fueling = _fueling_for(moving_s)

    workout = Workout(
        warmup=_warmup_block(segments[0], moving_s, profile),
        main=_main_blocks(segments, intensity, fueling, profile),
        cooldown=_cooldown_block(segments[-1], profile),
        summary_md=_summary(segments, moving_s, intensity, fueling),
        technical_focus=(
            "Gérer la course, pas le chrono : allure constante, ravitaillement à l'heure, "
            "transitions calmes et sans précipitation."
        ),
    )
    total_s = workout.total_duration_s()
    prep_h = (workout.warmup.duration_s + workout.cooldown.duration_s) / 3600
    race_tss = moving_s / 3600 * intensity.intensity_factor**2 * 100
    prep_tss = prep_h * _PREP_INTENSITY_FACTOR**2 * 100

    return {
        "date": day.isoformat(),
        "sport": race_sport,
        "session_type": "race",
        "target_duration_s": total_s,
        "target_tss": round(race_tss + prep_tss),
        "target_elevation_gain_m": sum(s.elevation_gain_m for s in segments),
        "phase": "race",
        "week_offset": week_offset,
        "workout": workout.model_dump(),
    }
