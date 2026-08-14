"""Plan orchestrator : reads profile + race_goal + activities, computes Banister
state, derives phases + sessions, writes to DB.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Any, cast

from garmin_sync.coach.activity_review import ActivityReview, build_activity_review
from garmin_sync.coach.banister import (
    BanisterState,
    cold_start_state,
    compute_banister_history,
    is_cold_start,
)
from garmin_sync.coach.discipline_level import load_effective_strengths
from garmin_sync.coach.duration_bounds import clamp_duration_to_bounds
from garmin_sync.coach.phases import Phase, compute_phases
from garmin_sync.coach.race_day import (
    CLIMB_HOURS_PER_1000M,
    RACE_SPEED_DEFAULT_KMH,
    RACE_SPEED_KMH,
    build_race_day_session,
)
from garmin_sync.coach.sports import normalize_discipline
from garmin_sync.coach.training_days import (
    allocate_sport_sessions,
    assign_sports,
    athlete_level,
    level_label_for_score,
    long_session_day,
    run_cap,
    select_training_days_observed,
    training_days_count,
)
from garmin_sync.coach.tss import compute_tss, resolve_fc_max_bpm
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

DbRows = list[dict[str, Any]]

_UTC_SUFFIX = "+00:00"


@dataclass(frozen=True)
class RaceTarget:
    """Ce que la course impose au plan : sa date, son sport et son profil d'effort.

    Regroupé (plutôt que passé paramètre par paramètre) pour garder les signatures
    de construction de semaine sous la limite de lisibilité : elles portaient 16 et
    17 paramètres, dont ceux-là, toujours transmis ensemble.
    """

    day: date
    sport: str
    time_shares: dict[str, float] | None = None
    dplus_by_sport: dict[str, int] | None = None
    # La course enchaîne un segment vélo puis un segment course à pied : le plan
    # doit alors contenir des séances d'enchaînement (#154).
    has_bike_run_transition: bool = False
    # Segments bruts + profil de performance : le jour J en dérive son temps
    # estimé, son TSS et son déroulé (issue #157). Absents -> case vide, comme avant.
    legs: list[dict[str, Any]] | None = None
    athlete: dict[str, Any] | None = None


@dataclass(frozen=True)
class ObservedHabits:
    """Ce que l'athlète fait réellement, mesuré sur son historique récent.

    Tout est optionnel : sans ces signaux le planner retombe sur ses répartitions
    par défaut (étalement mécanique des jours, D+ parti de zéro).
    """

    weekday_counts: dict[int, int] | None = None
    weekday_durations: dict[int, float] | None = None
    weekly_dplus: dict[str, int] | None = None


# Défaut partagé : la dataclass est frozen, donc sûre en singleton de module
# (et ruff B008 interdit de l'instancier dans une signature).
NO_OBSERVED_HABITS = ObservedHabits()


def _activity_day(raw: Any) -> date | None:
    """Jour d'une activité depuis son ``start_time``, ou None s'il est inutilisable.

    Garmin sérialise en ``...Z``, que ``fromisoformat`` ne sait pas lire avant
    Python 3.11 — le remplacement reste explicite pour rester lisible.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", _UTC_SUFFIX)).date()
    except ValueError:
        return None


# Ramp rates by phase / week index
NORMAL_RAMP_RATE = 1.05  # +5% per week (normal weeks)
DELOAD_RAMP_RATE = 0.70  # -30% deload week (every 4th week)
TAPER_RAMP_RATE = 0.55  # -45% taper

# Weekly ramp cap per sport (guardrail against overload)
WEEKLY_RAMP_CAP: dict[str, float] = {"run": 1.10, "swim": 1.15, "bike": 1.20}

DAY_NAME_TO_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def distribute_weekly_tss_by_sport(
    *,
    weekly_tss: float,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
    progress: float = 1.0,
) -> dict[str, float]:
    """Distribue le TSS hebdo entre sports selon le niveau par discipline.

    Niveau (1-5) module la part : faible (1) ~+25 %, fort (5) ~-15 % à biais plein.
    ``progress`` (0..1) module l'amplitude du biais via ``bias_curve`` : ~moitié du
    biais en début de plan, plein en fin de build. Normalisé (somme = weekly_tss).
    """
    p = min(1.0, max(0.0, progress))
    bias = 0.5 + 0.5 * p
    weights: dict[str, float] = {}
    for s in sports_in_race:
        score = sports_strengths.get(s, 3)
        boost = 0.25 - (score - 1) * 0.10  # niveau 1 -> +0.25, 3 -> 0, 5 -> -0.15
        weights[s] = 1.0 + boost * bias
    total_w = sum(weights.values())
    return {s: round(weekly_tss * w / total_w, 2) for s, w in weights.items()}


_HARD_TYPES_BY_LEVEL: dict[int, set[str]] = {
    1: set(),
    2: set(),
    3: {"threshold", "sprint"},
    4: {"threshold", "sprint", "pma"},
    5: {"threshold", "sprint", "pma"},
}

# Types dont l'accès dépend du niveau athlète (filtrés par _HARD_TYPES_BY_LEVEL).
# "intervals" reste dans le schéma/caps pour compatibilité (séances déjà en DB) mais
# n'apparaît plus dans aucune liste `base` ci-dessous — gardé ici uniquement pour ne
# jamais le laisser passer si une future liste `base` le réintroduit par erreur.
_FILTERABLE_HARD_TYPES = {"threshold", "intervals", "sprint", "pma"}


def pick_session_types_for_phase(
    phase: Phase, *, max_level: int = 5, progress: float = 1.0
) -> list[str]:
    """Return the canonical set of session types for a given phase.

    `max_level` (1-5) borne l'intensité : un niveau faible retire les types durs
    (threshold/pma/sprint) au profit d'endurance/recovery.

    `progress` (0..1, cf. `_progress_for_offset`) gate `pma` à la 2e moitié de la
    phase build (progress >= 0.5) — trop tôt dans le plan, pma n'apparaît pas
    encore. Par défaut 1.0 pour rester rétro-compatible avec les appels existants.
    """
    if phase == "base":
        base = ["endurance", "long", "recovery"]
    elif phase == "build":
        base = ["endurance", "threshold", "long"]
        if progress >= 0.5:
            base.append("pma")
    elif phase == "peak":
        base = ["pma", "sprint", "endurance", "long"]
    else:  # taper
        base = ["endurance", "recovery", "sprint"]

    allowed_hard = _HARD_TYPES_BY_LEVEL.get(max_level, {"threshold", "sprint", "pma"})
    filtered = [t for t in base if t not in _FILTERABLE_HARD_TYPES or t in allowed_hard]
    return filtered or ["endurance"]


def compute_week_load_multipliers(phases: Sequence[tuple[int, Phase]]) -> list[float]:
    """Cumulative weekly load multiplier per week (compounding +5% ramp).

    Normal build weeks apply the current progression then compound
    ``NORMAL_RAMP_RATE`` for the next week; deload (every 4th week) and taper weeks
    apply their reduction to the current progression WITHOUT advancing it (a
    step-back that resumes the build where it left off).

    Fixes the flat-load bug: previously every normal week got a fixed 1.05x of a
    CONSTANT base_weekly, so weeks 1, 2, 5, 9… were all identical and the only
    "progression" came from CTL drift between weekly regenerations (≈ nil).
    """
    multipliers: list[float] = []
    progression = 1.0
    for offset, phase in phases:
        is_deload = phase != "taper" and (offset + 1) % 4 == 0
        if phase == "taper":
            multipliers.append(round(progression * TAPER_RAMP_RATE, 4))
        elif is_deload:
            multipliers.append(round(progression * DELOAD_RAMP_RATE, 4))
        else:
            multipliers.append(round(progression, 4))
            progression *= NORMAL_RAMP_RATE
    return multipliers


def _progress_for_offset(offset: int, phases: Sequence[tuple[int, str]]) -> float:
    """Avancement 0..1 : 0 au début, 1 à la dernière semaine de build (tenu ensuite)."""
    build_offsets = [o for o, ph in phases if ph == "build"]
    if build_offsets:
        last = max(build_offsets)
    elif phases:
        last = phases[-1][0]
    else:
        last = 0
    return min(1.0, max(0.0, offset / max(1, last)))


def cap_weekly_ramp_by_sport(
    tss_by_sport: dict[str, float],
    prev_tss_by_sport: dict[str, float] | None,
) -> dict[str, float]:
    """Borne la hausse hebdo de TSS par sport (anti-surcharge, surtout course).

    Seules les hausses sont bridées (deload/taper intacts). Sans précédent pour un
    sport, pas de cap. L'excédent n'est pas redistribué (sécurité avant volume).
    """
    if not prev_tss_by_sport:
        return dict(tss_by_sport)
    capped: dict[str, float] = {}
    for sport, tss in tss_by_sport.items():
        prev = prev_tss_by_sport.get(sport)
        if prev is None or prev <= 0:
            capped[sport] = tss
            continue
        ceiling = prev * WEEKLY_RAMP_CAP.get(sport, 1.20)
        capped[sport] = round(min(tss, ceiling), 2)
    return capped


def _placement_priority_for_day(day_idx: int, long_day_idx: int | None = None) -> int:
    """Le jour "longue" est dérivé des jours d'entraînement retenus (#122) ;
    Mon/Thu (=0,3) get recovery; rest = mid-week.

    L'ancien codage en dur `day_idx == 6` (dimanche) ne matchait jamais les jours
    choisis par ``select_training_days`` -> 0 séance longue émise depuis mai.
    """
    if long_day_idx is not None and day_idx == long_day_idx:
        return 0  # long
    if day_idx in (0, 3):
        return 2  # recovery
    return 1


# Disciplines multi-segments : le jour de course porte la discipline du
# race_goal, pas celle du premier leg (#135 — un triathlon s'affichait comme
# une séance de natation). Le check DB accepte ces valeurs depuis la migration
# 20260801130000_planned_sessions_multisport.
_MULTI_SPORT_DISCIPLINES = {"triathlon", "duathlon", "aquathlon"}


def _race_day_sport(race: dict[str, Any]) -> str:
    discipline = str(race.get("discipline") or "")
    if discipline in _MULTI_SPORT_DISCIPLINES:
        return discipline
    legs = race.get("legs") or []
    if legs:
        return str(legs[0].get("discipline") or "run")
    return discipline or "run"


def _race_day_session(*, day: date, race: RaceTarget, week_offset: int) -> dict[str, Any]:
    """Jour J : temps estimé, TSS et déroulé par segment (cf. ``coach.race_day``)."""
    return build_race_day_session(
        day=day,
        race_sport=race.sport,
        week_offset=week_offset,
        legs=race.legs,
        athlete=race.athlete,
    )


def _rest_day_session(*, day: date, phase: Phase, week_offset: int) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "sport": "rest",
        "session_type": "rest",
        "target_duration_s": 0,
        "target_tss": 0,
        "target_elevation_gain_m": None,
        "phase": phase,
        "week_offset": week_offset,
    }


_HARD_SESSION_TYPES = {"threshold", "intervals", "pma", "sprint"}
_LONG_RECOVERY_TYPES = {"long", "recovery"}


def _pick_session_type(
    *,
    day_idx: int,
    types_for_phase: list[str],
    used_types: list[str],
    long_day_idx: int | None = None,
    sport_used_count: int = 0,
) -> str:
    """Pick a session type respecting priority slots and avoiding back-to-back hard sessions.

    ``types_for_phase`` est la liste de la DISCIPLINE du jour (plafond d'intensité
    par sport, cf. #121) ; ``used_types`` reste l'historique global de la semaine
    pour éviter deux séances dures d'affilée, tous sports confondus.

    ``sport_used_count`` (séances déjà posées pour CE sport cette semaine) sert la
    garantie de séance de qualité : le premier créneau éligible d'un sport prend
    un type dur si son niveau y donne droit — sans quoi l'index de rotation
    global retombait presque toujours sur "endurance" pour un sport n'ayant
    qu'un ou deux créneaux, et les semaines build/peak restaient sans intensité.
    """
    priority = _placement_priority_for_day(day_idx, long_day_idx)
    if priority == 0 and "long" in types_for_phase:
        return "long"
    if priority == 2 and "recovery" in types_for_phase:
        return "recovery"

    candidates = [t for t in types_for_phase if t not in _LONG_RECOVERY_TYPES]
    last = used_types[-1] if used_types else None
    if last in _HARD_SESSION_TYPES:
        candidates = [t for t in candidates if t not in _HARD_SESSION_TYPES]
    if not candidates:
        return "endurance"
    hard = [t for t in candidates if t in _HARD_SESSION_TYPES]
    if sport_used_count == 0 and hard:
        return hard[0]
    soft = [t for t in candidates if t not in _HARD_SESSION_TYPES]
    pool = soft or candidates
    return pool[len(used_types) % len(pool)]


# Relative TSS weights by session type. "long" gets ~50% more, "recovery"
# half, etc. — keeps the weekly TSS budget but redistributes within each sport.
_SESSION_TYPE_WEIGHT: dict[str, float] = {
    "long": 1.5,
    "threshold": 1.2,
    "intervals": 1.2,
    "pma": 1.2,
    "sprint": 0.9,
    "endurance": 1.0,
    "recovery": 0.5,
}


# Average TSS/hour per (sport, session_type). Drives the TSS -> duration mapping.
# Same TSS budget produces different durations across sports because the
# physiological load per unit time differs (bike low cadence Z2 vs run Z2).
# Reference points (sport scientists, TR/TP heuristics):
#   - Bike Z2 endurance: IF ~0.65-0.70 -> TSS/h ~ 42-49
#   - Run Z2 endurance:  rTSS ~50-60
#   - Swim Z2:           sTSS ~55-65 (skill-limited)
#   - Intervals/threshold: IF 0.85-0.95+ -> 75-95 TSS/h
_TSS_PER_HOUR: dict[tuple[str, str], float] = {
    ("bike", "endurance"): 40.0,
    ("bike", "long"): 45.0,
    ("bike", "threshold"): 72.0,
    ("bike", "intervals"): 82.0,
    ("bike", "pma"): 88.0,
    ("bike", "sprint"): 65.0,
    ("bike", "recovery"): 22.0,
    ("run", "endurance"): 48.0,
    ("run", "long"): 52.0,
    ("run", "threshold"): 75.0,
    ("run", "intervals"): 90.0,
    ("run", "pma"): 95.0,
    ("run", "sprint"): 70.0,
    ("run", "recovery"): 30.0,
    ("swim", "endurance"): 50.0,
    ("swim", "long"): 55.0,
    ("swim", "threshold"): 72.0,
    ("swim", "intervals"): 85.0,
    ("swim", "pma"): 88.0,
    ("swim", "sprint"): 68.0,
    ("swim", "recovery"): 35.0,
    ("brick", "endurance"): 65.0,
    ("brick", "long"): 65.0,
}
_TSS_PER_HOUR_DEFAULT = 50.0


def _tss_per_hour(sport: str, stype: str) -> float:
    return _TSS_PER_HOUR.get((sport, stype), _TSS_PER_HOUR_DEFAULT)


# TSS/h moyen pondéré d'une semaine type (Z2 dominant) pour convertir les heures
# déclarées en budget TSS de faisabilité.
_AVG_WEEKLY_TSS_PER_HOUR = 45.0


def weekly_tss_cap_from_hours(hours_per_week: float | None) -> int:
    """Budget TSS hebdo maximal dérivé des heures déclarées (0 = pas de budget)."""
    if not hours_per_week:
        return 0
    return round(hours_per_week * _AVG_WEEKLY_TSS_PER_HOUR)


def compute_base_weekly_tss(*, ctl: float, hours_per_week: float | None) -> float:
    """Volume hebdo de départ : le CTL MESURÉ est la source primaire, les heures
    déclarées un plafond de faisabilité — plus jamais un plancher (#128).

    Bug prod : ``max(ctl*7, heures*45)`` faisait piloter le plan par la
    déclaration d'onboarding (360 TSS) au lieu du réel mesuré (147) — le plan
    exigeait 2,3x la charge de l'athlète et « load_spike » devenait permanent.
    Le ramp hebdo (+5 %) fait converger progressivement la charge mesurée vers
    le budget déclaré au fil du plan, au lieu de l'imposer d'emblée.

    NOTE #120 : tant que le TSS approxime ``durée x 50``, le CTL reste un proxy
    de volume. Cette fonction ne consomme que ``ctl`` : elle devient juste
    automatiquement dès que le calcul du TSS est corrigé.
    """
    measured = max(0.0, ctl) * 7
    cap = weekly_tss_cap_from_hours(hours_per_week)
    if cap <= 0:
        return measured
    if measured <= 0:
        # Aucun historique : on repart du budget déclaré (seul signal dispo).
        return float(cap)
    return float(min(measured, cap))


# Minimum per-sport race elevation gain (m) below which we don't bother training
# hills. A 50m run race or a 200m bike race is flat enough that "spécificité
# terrain" doesn't justify dedicated hill sessions.
_ELEVATION_THRESHOLD_M: dict[str, int] = {
    "bike": 300,
    "run": 100,
    "swim": 1_000_000,  # never
    "brick": 200,
}

# Per-session weight for distributing the weekly elevation target. Long absorbs
# most of the D+, intervals/recovery zero (pma/sprint are typically track-based;
# intervals is kept only for schema compatibility, no longer emitted).
_ELEVATION_SESSION_WEIGHT: dict[str, float] = {
    "long": 2.0,
    "endurance": 1.0,
    "threshold": 0.3,
    "intervals": 0.0,
    "pma": 0.0,
    "sprint": 0.0,
    "recovery": 0.0,
    "race": 1.0,
    "rest": 0.0,
}

# Plafond de gradient (mètres de D+ par heure) admissible pour UNE séance (#158).
#
# Le poids « long » (2.0) empilait la cible hebdo sur la sortie longue : 1920 m
# sur 2 h de vélo en prod (~960 m/h), plus raide que la course préparée
# (~700 m/h sur sa partie vélo). Les valeurs ci-dessous sont calées sur
# l'exigence réelle d'une épreuve montagneuse — le plan peut viser le gradient
# de la course, pas le dépasser franchement — et sur ce qu'un amateur tient sur
# la durée COMPLÈTE d'une séance (montées + plat + descentes, pas la seule
# vitesse ascensionnelle d'un col).
ELEVATION_GRADIENT_CAP_M_PER_H: dict[str, float] = {
    "bike": 700.0,
    "run": 500.0,
    "brick": 600.0,
}
_ELEVATION_GRADIENT_CAP_DEFAULT = 500.0

# Contrainte DB : target_elevation_gain_m <= 5000 m par séance.
_ELEVATION_SESSION_MAX_M = 5000


def session_elevation_cap_m(sport: str, duration_s: int) -> int:
    """D+ maximal admissible pour une séance de ``duration_s`` dans ce sport."""
    gradient = ELEVATION_GRADIENT_CAP_M_PER_H.get(sport, _ELEVATION_GRADIENT_CAP_DEFAULT)
    return min(_ELEVATION_SESSION_MAX_M, round(gradient * max(0, duration_s) / 3600))


def _redistribute_elevation(targets: list[int], caps: list[int]) -> tuple[list[int], int]:
    """Borne chaque cible par son plafond, reporte le surplus, écrête le reste.

    Retourne ``(cibles bornées, mètres écrêtés)``. Le report est proportionnel à
    la marge restante de chaque séance : le volume hebdo de D+ est conservé tant
    qu'il rentre quelque part, seule sa répartition change.
    """
    allotted = [min(t, c) for t, c in zip(targets, caps, strict=True)]
    surplus = sum(targets) - sum(allotted)
    if surplus <= 0:
        return allotted, 0

    headroom = [c - a for c, a in zip(caps, allotted, strict=True)]
    total_headroom = sum(headroom)
    take = min(surplus, total_headroom)
    if take <= 0:
        return allotted, surplus

    placed = 0
    for i, room in enumerate(headroom):
        if room <= 0:
            continue
        add = min(room, take * room // total_headroom)
        allotted[i] += add
        placed += add
    # Reliquat d'arrondi (< nombre de séances) : sur la plus grosse marge d'abord.
    remainder = take - placed
    for i in sorted(range(len(allotted)), key=lambda j: caps[j] - allotted[j], reverse=True):
        if remainder <= 0:
            break
        add = min(caps[i] - allotted[i], remainder)
        allotted[i] += add
        remainder -= add
    return allotted, surplus - take + remainder


def cap_session_elevation_gradients(sessions: list[dict[str, Any]]) -> int:
    """Rend la répartition hebdo du D+ réalisable séance par séance (#158).

    Aucune séance ne dépasse ``ELEVATION_GRADIENT_CAP_M_PER_H`` pour son sport ;
    le surplus part sur les autres séances DU MÊME SPORT qui ont de la marge, et
    n'est écrêté qu'en dernier recours. Retourne le total (m) écrêté — une
    semaine trop pentue pour être répartie est tracée, jamais silencieuse.
    """
    by_sport: dict[str, list[dict[str, Any]]] = {}
    for s in sessions:
        if not s.get("target_elevation_gain_m"):
            continue
        by_sport.setdefault(str(s.get("sport") or ""), []).append(s)

    clipped_total = 0
    for sport, group in by_sport.items():
        caps = [session_elevation_cap_m(sport, int(s.get("target_duration_s") or 0)) for s in group]
        targets = [int(s["target_elevation_gain_m"]) for s in group]
        allotted, clipped = _redistribute_elevation(targets, caps)
        for session, value in zip(group, allotted, strict=True):
            session["target_elevation_gain_m"] = value if value > 0 else None
        if clipped <= 0:
            continue
        clipped_total += clipped
        log.warning(
            "elevation gradient cap: %d m écrêtés en %s (%d séance(s), cible hebdo %d m)",
            clipped,
            sport,
            len(group),
            sum(targets),
        )
    return clipped_total


_FIRST_WEEK_STRONG_DELOAD_SIGNALS = {"return_after_break", "load_spike", "hard_sessions_density"}
_FIRST_WEEK_LIGHT_DELOAD_SIGNALS = {"recent_long_session", "elevation_spike"}


def compute_first_week_tss_multiplier(activity_review: ActivityReview) -> float:
    """Return a conservative first-week TSS multiplier from recent coach signals."""
    names = {insight.name for insight in activity_review.insights}
    if names & _FIRST_WEEK_STRONG_DELOAD_SIGNALS:
        return 0.85
    if names & _FIRST_WEEK_LIGHT_DELOAD_SIGNALS:
        return 0.92
    return 1.0


def estimate_race_time_shares(legs: list[dict[str, Any]]) -> dict[str, float]:
    """Part du temps de course estimé par discipline (somme = 1).

    C'est l'ENJEU de l'épreuve — pas l'ordre chronologique des legs — qui doit
    piloter la répartition des séances (#130). Les segments d'une même
    discipline s'additionnent (duathlon run-bike-run). Sans legs exploitables,
    parts égales.

    Vitesses de référence partagées avec ``coach.race_day`` : le temps estimé du
    jour J et la répartition des séances de préparation décrivent la même course.
    """
    hours: dict[str, float] = {}
    for leg in legs:
        disc = str(leg.get("discipline") or "unknown")
        dist = float(leg.get("distance_km") or 0)
        dplus = float(leg.get("elevation_gain_m") or 0)
        h = dist / RACE_SPEED_KMH.get(disc, RACE_SPEED_DEFAULT_KMH)
        h += dplus / 1000 * CLIMB_HOURS_PER_1000M
        hours[disc] = hours.get(disc, 0.0) + h
    total = sum(hours.values())
    if total <= 0:
        return {s: 1.0 / len(hours) for s in hours} if hours else {}
    return {s: h / total for s, h in hours.items()}


# Séances d'enchaînement (#154) : phases où un brick a sa place, et types
# autorisés (les seuls que ``_TSS_PER_HOUR`` connaît pour le brick).
_BRICK_PHASES = frozenset({"build", "peak"})
_BRICK_SESSION_TYPES = ["endurance", "long"]
# Disciplines dont le brick consomme le volume : il s'y substitue, il ne s'ajoute pas.
_BRICK_SOURCE_SPORTS = ("bike", "run")
# Poids du brick dans ce budget vélo + CAP : une sortie vélo pleine PLUS la
# course qui l'enchaîne, donc plus qu'une séance ordinaire du même budget.
_BRICK_TSS_WEIGHT = 1.5


def race_has_bike_run_transition(legs: list[dict[str, Any]]) -> bool:
    """La course enchaîne-t-elle un segment vélo puis un segment course à pied ?

    C'est la transition que le brick prépare (triathlon, duathlon). Un
    aquathlon (natation -> course) répond False : les tables TSS/heure et la
    vitesse de référence du brick décrivent un vélo -> CAP, pas un swim -> run.
    """
    disciplines = [str(leg.get("discipline") or "") for leg in legs]
    return any(first == "bike" and second == "run" for first, second in pairwise(disciplines))


def _tss_with_brick_share(
    tss_by_sport: dict[str, float], sport_counts: dict[str, int]
) -> dict[str, float]:
    """Donne au brick sa part du budget hebdo, PRISE sur le vélo et la CAP.

    Sans cette redistribution le brick hériterait d'un TSS nul (il n'est pas une
    discipline de la course, donc absent de ``distribute_weekly_tss_by_sport``).
    Vélo et CAP sont réduits au prorata de leur charge : le budget hebdo total
    est conservé, le brick se substitue au volume au lieu de s'y ajouter.
    """
    n_brick = sport_counts.get("brick", 0)
    if n_brick <= 0:
        return tss_by_sport
    pool = sum(tss_by_sport.get(s, 0.0) for s in _BRICK_SOURCE_SPORTS)
    n_source = sum(sport_counts.get(s, 0) for s in _BRICK_SOURCE_SPORTS)
    brick_weight = n_brick * _BRICK_TSS_WEIGHT
    if pool <= 0 or n_source <= 0:
        return tss_by_sport
    brick_ratio = brick_weight / (n_source + brick_weight)
    out = dict(tss_by_sport)
    for sport in _BRICK_SOURCE_SPORTS:
        out[sport] = round(tss_by_sport.get(sport, 0.0) * (1 - brick_ratio), 2)
    out["brick"] = round(pool * brick_ratio, 2)
    return out


def compute_elevation_per_sport(legs: list[dict[str, Any]]) -> dict[str, int]:
    """Sum the race's total D+ per sport from its legs.

    Returns a {sport: meters} map. Sports missing from legs default to 0.
    """
    by_sport: dict[str, int] = {}
    for leg in legs:
        sport = leg.get("discipline", "unknown")
        gain = int(leg.get("elevation_gain_m") or 0)
        by_sport[sport] = by_sport.get(sport, 0) + gain
    return by_sport


def _training_day_session(
    *,
    day: date,
    phase: Phase,
    week_offset: int,
    stype: str,
    sport: str,
    tss_by_sport: dict[str, float],
    sport_weight_total: dict[str, float],
    weekly_elevation_by_sport: dict[str, int],
    sport_elevation_weight_total: dict[str, float],
) -> dict[str, Any]:
    """Build one training day's session.

    Per-day TSS = sport_tss * (this_session_weight / sum_of_session_weights_for_this_sport).
    This keeps the weekly TSS budget intact while letting "long" sessions get more
    volume than e.g. "recovery".

    The session type and sport are decided upstream (single-pass day plan) so the
    weight tallies and the emitted sessions never diverge. Durations are clamped to
    realistic per (sport, type, phase) bounds.

    target_elevation_gain_m is populated only when the sport has a meaningful
    weekly D+ target (set by the caller via weekly_elevation_by_sport). Same
    redistribution scheme as TSS, but with a separate weight table (long heavy,
    intervals zero — intervals are typically track-based).
    """
    sport_tss = tss_by_sport.get(sport, 0)
    weight = _SESSION_TYPE_WEIGHT.get(stype, 1.0)
    total_weight = max(0.5, sport_weight_total.get(sport, 1.0))
    per_day_tss = sport_tss * weight / total_weight
    duration_s = int(per_day_tss * 3600 / _tss_per_hour(sport, stype))
    duration_s = clamp_duration_to_bounds(sport, stype, phase, duration_s)
    # Re-derive the TSS from the (possibly clamped) duration so duration, TSS and
    # intensity stay internally consistent — the LLM prompt and the prévu/réalisé
    # comparisons read target_tss, and a stale pre-clamp value would force the
    # intensity up. Trade-off: the weekly TSS budget is no longer exactly conserved.
    per_day_tss = duration_s / 3600 * _tss_per_hour(sport, stype)

    target_elevation: int | None = None
    weekly_dplus = weekly_elevation_by_sport.get(sport, 0)
    if weekly_dplus > 0:
        elev_weight = _ELEVATION_SESSION_WEIGHT.get(stype, 0.0)
        elev_total = max(0.5, sport_elevation_weight_total.get(sport, 1.0))
        if elev_weight > 0:
            # Borné par la contrainte DB (<= 5000 m par séance).
            target_elevation = min(5000, round(weekly_dplus * elev_weight / elev_total))

    return {
        "date": day.isoformat(),
        "sport": sport,
        "session_type": stype,
        "target_duration_s": duration_s,
        "target_tss": round(per_day_tss, 2),
        "target_elevation_gain_m": target_elevation,
        "phase": phase,
        "week_offset": week_offset,
    }


def _build_training_day_plan(
    *,
    week_start: date,
    training_idx: set[int],
    sport_by_day: dict[int, str],
    types_by_sport: dict[str, list[str]],
    is_last_week: bool,
    race_date: date,
    long_day_idx: int | None = None,
) -> dict[int, tuple[str, str]]:
    """Single-pass day plan: weekday index -> (sport, session_type).

    Walks the 7 days in order so `_pick_session_type`'s used_types history is
    consistent with the emission loop. Only days selected as training days
    (and not the race day) get an entry. Both the weight tallies and the emitted
    sessions derive from this map, so they can never diverge.

    ``types_by_sport`` porte le plafond d'intensité PAR discipline (#121) : le
    type du jour est tiré de la liste du sport assigné à ce jour — un niveau 1
    en course n'interdit plus le seuil en vélo.
    """
    plan: dict[int, tuple[str, str]] = {}
    used_types: list[str] = []
    sport_counts: dict[str, int] = {}
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()
        if is_last_week and day == race_date:
            continue
        if day_idx not in training_idx:
            continue
        sport = sport_by_day.get(day_idx, "run")
        stype = _pick_session_type(
            day_idx=day_idx,
            types_for_phase=types_by_sport.get(sport, ["endurance"]),
            used_types=used_types,
            long_day_idx=long_day_idx,
            sport_used_count=sport_counts.get(sport, 0),
        )
        used_types.append(stype)
        sport_counts[sport] = sport_counts.get(sport, 0) + 1
        plan[day_idx] = (sport, stype)
    return plan


def _tally_sport_weights(
    plan: dict[int, tuple[str, str]], weight_table: dict[str, float]
) -> dict[str, float]:
    """Sum a per-session-type weight per sport over the day plan."""
    totals: dict[str, float] = {}
    for sport, stype in plan.values():
        totals[sport] = totals.get(sport, 0.0) + weight_table.get(stype, 0.0)
    return totals


# Point de départ de la progression D+ quand aucun historique n'est observé
# (fraction du D+ de course), et facteur de réduction en taper.
_ELEVATION_START_FRACTION = 0.4
_ELEVATION_TAPER_FACTOR = 0.3

# Fenêtre d'observation du D+ réellement encaissé par l'athlète.
_ELEVATION_OBSERVED_WINDOW_DAYS = 28


def observed_weekly_elevation_by_sport(
    activities: list[dict[str, Any]],
    *,
    today: date,
    window_days: int = _ELEVATION_OBSERVED_WINDOW_DAYS,
) -> dict[str, int]:
    """D+ hebdo moyen réellement encaissé par discipline sur la fenêtre récente.

    Sert de point de départ à la progression de dénivelé (#131) : l'athlète qui
    encaisse déjà 2000 m/sem ne doit pas se voir prescrire 500 m — puis être
    alerté « elevation_spike » dans le même briefing.
    """
    start = today - timedelta(days=window_days)
    totals: dict[str, float] = {}
    for a in activities:
        d = _activity_day(a.get("start_time"))
        if d is None or not (start <= d <= today):
            continue
        disc = normalize_discipline(str(a.get("sport") or ""))
        if disc is None:
            continue
        totals[disc] = totals.get(disc, 0.0) + float(a.get("elevation_gain_m") or 0)
    weeks = window_days / 7
    return {s: round(v / weeks) for s, v in totals.items()}


# Fenêtre d'observation des habitudes de placement (jours réellement utilisés).
_WEEKDAY_USAGE_WINDOW_DAYS = 28


def observed_weekday_usage(
    activities: list[dict[str, Any]],
    *,
    today: date,
    window_days: int = _WEEKDAY_USAGE_WINDOW_DAYS,
) -> tuple[dict[int, int], dict[int, float]]:
    """(séances, durée cumulée) par jour de semaine sur la fenêtre récente (#127).

    Sert à caler la grille d'entraînement sur les jours que l'athlète UTILISE
    réellement (et la séance longue sur son jour de grosse sortie), plutôt que
    de reproposer chaque semaine un étalement mécanique jamais suivi.
    """
    start = today - timedelta(days=window_days)
    counts: dict[int, int] = {}
    durations: dict[int, float] = {}
    for a in activities:
        d = _activity_day(a.get("start_time"))
        if d is None or not (start <= d <= today):
            continue
        weekday = d.weekday()
        counts[weekday] = counts.get(weekday, 0) + 1
        durations[weekday] = durations.get(weekday, 0.0) + float(a.get("duration_s") or 0)
    return counts, durations


def compute_weekly_elevation_targets(
    *,
    race_dplus_by_sport: dict[str, int],
    week_offset: int,
    phases: Sequence[tuple[int, Phase]],
    observed_weekly_dplus: dict[str, int] | None = None,
) -> dict[str, int]:
    """Weekly D+ target per sport : progression vers un PIC, plus un étalement.

    L'ancien modèle divisait le D+ total de la course par les semaines du plan
    (2000 m -> 500 m/sem) : aucune semaine n'approchait jamais la contrainte
    réelle de l'épreuve, et la cible restait sous ce que l'athlète encaissait
    déjà (#131). Ici :

    - point de départ = D+ hebdo OBSERVÉ (ou ``_ELEVATION_START_FRACTION`` du
      D+ de course sans historique) ;
    - croissance géométrique bornée par ``WEEKLY_RAMP_CAP`` (cohérent avec le
      cap TSS), calée pour atteindre >= 100 % du D+ de course à la dernière
      semaine hors taper ;
    - taper : réduction franche (``_ELEVATION_TAPER_FACTOR``).

    Ancrée sur ``week_offset`` (grille immuable, #123) : la cible d'une semaine
    calendaire ne change plus d'une régénération à l'autre. Sports sous
    ``_ELEVATION_THRESHOLD_M`` : cible 0 (pas de travail de côte nécessaire).
    """
    observed = observed_weekly_dplus or {}
    non_taper = [o for o, ph in phases if ph != "taper"]
    peak_offset = max(non_taper, default=0)
    phase_by_offset: dict[int, str] = dict(phases)
    phase = phase_by_offset.get(week_offset, "build")

    out: dict[str, int] = {}
    for sport, total in race_dplus_by_sport.items():
        threshold = _ELEVATION_THRESHOLD_M.get(sport, 200)
        if total < threshold:
            out[sport] = 0
            continue
        peak_target = float(total)
        start = float(observed.get(sport) or 0) or peak_target * _ELEVATION_START_FRACTION
        start = min(start, peak_target)
        cap = WEEKLY_RAMP_CAP.get(sport, 1.20)
        if peak_offset > 0 and start < peak_target:
            growth = min(cap, (peak_target / start) ** (1 / peak_offset))
        else:
            growth = 1.0
        target = min(peak_target, start * growth**week_offset)
        if phase == "taper":
            target *= _ELEVATION_TAPER_FACTOR
        out[sport] = round(target)
    return out


def _build_week_sessions(
    *,
    week_offset: int,
    phase: Phase,
    week_start: date,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
    tss_by_sport: dict[str, float],
    available_days: list[str],
    hours_per_week: float | None,
    is_last_week: bool,
    race: RaceTarget,
    weekly_elevation_by_sport: dict[str, int] | None = None,
    progress: float = 1.0,
    observed: ObservedHabits = NO_OBSERVED_HABITS,
) -> list[dict[str, Any]]:
    """Generate one week's planned sessions.

    ``available_days`` is treated as a MASK of possible windows: the effective
    number of training days is capped by volume/level/rest-floor
    (``training_days_count``), the chosen days are spread out
    (``select_training_days``), the per-sport session counts follow the race's
    time shares (``allocate_sport_sessions``, #130), sports are placed on days
    (``assign_sports``: run cap, no back-to-back run, dominant sport on the
    long day), and the resulting day plan drives both the weight tallies and
    the emitted sessions in a single pass.
    """
    weekly_elevation_by_sport = weekly_elevation_by_sport or {}
    sessions: list[dict[str, Any]] = []

    level = athlete_level(sports_strengths)
    # Plafond d'intensité PAR discipline (#121) : le min global verrouillait
    # l'intensité de TOUS les sports sur la discipline la plus faible.
    types_by_sport = {
        s: pick_session_types_for_phase(
            phase, max_level=sports_strengths.get(s, 3), progress=progress
        )
        for s in sports_in_race
    }
    available_idx = {DAY_NAME_TO_INDEX[d] for d in available_days if d in DAY_NAME_TO_INDEX}

    # Deload weeks (every 4th, except taper) need a stricter rest floor.
    is_deload = (week_offset + 1) % 4 == 0
    phase_for_rest = "deload" if is_deload and phase != "taper" else phase
    count = training_days_count(
        n_available=len(available_idx), hours=hours_per_week, level=level, phase=phase_for_rest
    )
    # Jours calés sur les habitudes observées de l'athlète (#127) — la grille
    # mécanique jamais suivie générait 0 correspondance prévu/réalisé.
    training_idx = select_training_days_observed(
        available_idx=available_idx, count=count, weekday_counts=observed.weekday_counts
    )
    long_day_idx = long_session_day(training_idx, weekday_durations=observed.weekday_durations)
    # Répartition des séances par l'enjeu de course (#130), pas par l'ordre des
    # legs. Sans parts fournies (anciens appels), parts égales.
    equal = {s: 1.0 / len(sports_in_race) for s in sports_in_race} if sports_in_race else {}
    shares = race.time_shares or equal
    # Cap course PAR discipline (#129) : c'est le niveau run — pas le niveau
    # global — qui borne l'impact traumatisant de la course a pied.
    run_level = level_label_for_score(sports_strengths.get("run", 3))
    # Enchaînement vélo->CAP (#154) : réservé aux phases build/peak d'une course
    # à transition — jamais en taper (semaine de course) ni en base.
    with_brick = race.has_bike_run_transition and phase in _BRICK_PHASES
    sport_counts = allocate_sport_sessions(
        count=count,
        time_shares=shares,
        strengths=sports_strengths,
        run_cap_value=run_cap(run_level) if "run" in sports_in_race else None,
        with_brick=with_brick,
    )
    if "brick" in sport_counts:
        types_by_sport["brick"] = _BRICK_SESSION_TYPES
        tss_by_sport = _tss_with_brick_share(tss_by_sport, sport_counts)
    sport_by_day = assign_sports(
        training_idx=sorted(training_idx), sport_counts=sport_counts, long_day_idx=long_day_idx
    )

    # Single-pass day plan so weight tallies and emitted sessions never diverge.
    day_plan = _build_training_day_plan(
        week_start=week_start,
        training_idx=training_idx,
        sport_by_day=sport_by_day,
        types_by_sport=types_by_sport,
        is_last_week=is_last_week,
        race_date=race.day,
        long_day_idx=long_day_idx,
    )
    sport_weight_total = _tally_sport_weights(day_plan, _SESSION_TYPE_WEIGHT)
    sport_elev_weight_total = _tally_sport_weights(day_plan, _ELEVATION_SESSION_WEIGHT)

    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()

        if is_last_week and day == race.day:
            sessions.append(_race_day_session(day=day, race=race, week_offset=week_offset))
            continue
        if day_idx not in day_plan:
            sessions.append(_rest_day_session(day=day, phase=phase, week_offset=week_offset))
            continue

        sport, stype = day_plan[day_idx]
        sessions.append(
            _training_day_session(
                day=day,
                phase=phase,
                week_offset=week_offset,
                stype=stype,
                sport=sport,
                tss_by_sport=tss_by_sport,
                sport_weight_total=sport_weight_total,
                weekly_elevation_by_sport=weekly_elevation_by_sport,
                sport_elevation_weight_total=sport_elev_weight_total,
            )
        )
    # Le poids « long » concentre la cible hebdo sur une seule sortie : on la
    # rend réalisable (plafond de gradient + report sur les séances qui ont de
    # la marge) sans toucher au volume hebdo visé (#158).
    cap_session_elevation_gradients(sessions)
    return sessions


def _compute_tss_by_date(
    activities: list[dict[str, Any]], profile: dict[str, Any], *, today: date
) -> dict[date, float]:
    """Aggregate per-day TSS from a list of activity rows.

    La FCmax passe par ``resolve_fc_max_bpm`` (#120/#134) : valeur profil si
    renseignée, sinon max des ``hr_max`` observés sur 90 j. Sans ce fallback,
    ``fc_max_bpm`` NULL en prod faisait retomber tout le calcul sur le tier
    « durée x 50 » et le CTL du planner divergeait du reste du système.
    """
    tss_by_date: dict[date, float] = {}
    ftp = profile.get("ftp_watts")
    fc_max = resolve_fc_max_bpm(profile.get("fc_max_bpm"), activities, today=today)
    for a in activities:
        tss = compute_tss(
            duration_s=a.get("duration_s", 0),
            sport=a.get("sport", ""),
            power_avg=a.get("power_avg"),
            hr_avg=a.get("hr_avg"),
            ftp_watts=ftp,
            fc_max_bpm=fc_max,
        )
        if tss is None:
            continue
        d = _activity_day(a.get("start_time"))
        if d is None:
            continue
        tss_by_date[d] = tss_by_date.get(d, 0.0) + tss
    return tss_by_date


def _load_today_banister_state(
    *, db: Any, user_id: str, profile: dict[str, Any], today: date
) -> tuple[dict[date, float], BanisterState, ActivityReview, list[dict[str, Any]]]:
    """Load last 180 days of activities, derive tss_by_date and today's CTL/ATL/TSB.

    Cold-start (``is_cold_start``): skip the 180-day decay simulation and use the
    shared ``cold_start_state`` (#134 — implémentation unique avec state.py) as
    today's state directly. See cold-start regression test for the rationale.

    Returns (tss_by_date, banister_state, activity_review, activities).
    """
    history_start = today - timedelta(days=180)
    activities = cast(
        DbRows,
        db.table("activities")
        .select("start_time, sport, duration_s, power_avg, hr_avg, hr_max, tss, elevation_gain_m")
        .eq("user_id", user_id)
        .gte("start_time", history_start.isoformat())
        .execute()
        .data
        or [],
    )
    tss_by_date = _compute_tss_by_date(activities, profile, today=today)
    activity_review = build_activity_review(activities, today=today)

    if is_cold_start(tss_by_date):
        return (
            tss_by_date,
            cold_start_state(profile.get("hours_per_week")),
            activity_review,
            activities,
        )

    states = compute_banister_history(
        tss_by_date=tss_by_date,
        start=history_start,
        end=today,
        initial_ctl=0.0,
        initial_atl=0.0,
    )
    return tss_by_date, states[-1], activity_review, activities


def _build_all_week_sessions(
    *,
    phases: Sequence[tuple[int, Phase]],
    today_state: BanisterState,
    profile: dict[str, Any],
    first_week_tss_multiplier: float,
    sports_in_race: list[str],
    effective_strengths: dict[str, int],
    available_days: list[str],
    weeks_count: int,
    week_start: date,
    race: RaceTarget,
    current_offset: int = 0,
    observed: ObservedHabits = NO_OBSERVED_HABITS,
) -> list[dict[str, Any]]:
    """Build planned sessions for all weeks of the plan.

    ``current_offset`` est la semaine qui contient `today` dans la grille ancrée
    (#123) : c'est elle — et non plus l'offset 0, potentiellement passé — qui
    reçoit le multiplicateur prudent de première semaine.
    """
    all_sessions: list[dict[str, Any]] = []
    prev_tss_by_sport: dict[str, float] | None = None
    load_multipliers = compute_week_load_multipliers(phases)
    base_weekly = compute_base_weekly_tss(
        ctl=today_state.ctl, hours_per_week=profile.get("hours_per_week")
    )
    hours_cap = weekly_tss_cap_from_hours(profile.get("hours_per_week"))
    for i, (offset, phase) in enumerate(phases):
        # Cible D+ par semaine : progression ancrée vers un pic en fin de build,
        # partant du D+ réellement encaissé, réduite en taper (#131).
        weekly_elevation_by_sport = compute_weekly_elevation_targets(
            race_dplus_by_sport=race.dplus_by_sport or {},
            week_offset=offset,
            phases=phases,
            observed_weekly_dplus=observed.weekly_dplus,
        )
        weekly_tss = base_weekly * load_multipliers[i]
        if hours_cap > 0:
            # Le ramp converge vers le budget déclaré mais ne le dépasse pas :
            # les heures dispo restent un plafond de faisabilité (#128).
            weekly_tss = min(weekly_tss, float(hours_cap))
        if offset == current_offset:
            weekly_tss *= first_week_tss_multiplier
        progress = _progress_for_offset(offset, phases)
        tss_by_sport = distribute_weekly_tss_by_sport(
            weekly_tss=weekly_tss,
            sports_in_race=sports_in_race,
            sports_strengths=effective_strengths,
            progress=progress,
        )
        tss_by_sport = cap_weekly_ramp_by_sport(tss_by_sport, prev_tss_by_sport)
        is_reduction_week = phase == "taper" or (offset + 1) % 4 == 0
        if not is_reduction_week:
            prev_tss_by_sport = tss_by_sport
        is_last = offset == weeks_count - 1
        sessions = _build_week_sessions(
            week_offset=offset,
            phase=phase,
            week_start=week_start + timedelta(weeks=offset),
            sports_in_race=sports_in_race,
            sports_strengths=effective_strengths,
            tss_by_sport=tss_by_sport,
            available_days=available_days,
            hours_per_week=profile.get("hours_per_week"),
            is_last_week=is_last,
            race=race,
            weekly_elevation_by_sport=weekly_elevation_by_sport,
            progress=progress,
            observed=observed,
        )
        all_sessions.extend(sessions)
    return all_sessions


def _workout_carry_key(session: dict[str, Any]) -> tuple[Any, ...]:
    """Identity used to reuse a workout across a regeneration.

    Same day, same sport, same type AND same target duration: anything else means
    the session actually changed and the previous workout no longer fits its
    numeric envelope.
    """
    return (
        session.get("date"),
        session.get("sport"),
        session.get("session_type"),
        session.get("target_duration_s"),
    )


def carry_over_workouts(
    new_sessions: list[dict[str, Any]], existing_sessions: Sequence[dict[str, Any]]
) -> int:
    """Copy already-generated (already PAID) workouts onto identical new sessions.

    The weekly regeneration used to drop every workout: each Monday the athlete
    found empty sessions and the LLM re-billed the exact same generations. Returns
    how many workouts were reused.

    Une séance qui porte DÉJÀ son contenu (le jour de course, calculé sans LLM)
    n'est jamais écrasée : sinon une version périmée, calculée sur un profil ou
    des legs antérieurs, remplacerait silencieusement celle qu'on vient de bâtir.
    """
    by_key = {_workout_carry_key(s): s for s in existing_sessions if s.get("workout") is not None}
    reused = 0
    for session in new_sessions:
        if session.get("workout") is not None:
            continue
        previous = by_key.get(_workout_carry_key(session))
        if previous is None:
            continue
        session["workout"] = previous["workout"]
        session["workout_generated_at"] = previous.get("workout_generated_at")
        reused += 1
    return reused


# Garde-fou : la contrainte DB borne training_plans.weeks_count à 52. Une ancre
# trop ancienne (course décalée d'un an, données legacy) ne doit pas la violer.
_MAX_PREP_WEEKS = 52


def _ensure_prep_anchor(db: Any, race: dict[str, Any], *, today: date, race_date: date) -> date:
    """Retourne l'ancre IMMUABLE du début de préparation (#123).

    Posée à la première génération (prep_start_date = today) puis réutilisée
    telle quelle : les phases et week_offset se calculent depuis cette date,
    pas depuis `today` — sinon l'horizon rétrécit à chaque régénération hebdo
    et l'athlète reste coincé en début de plan (jamais de peak, retours
    build -> base observés en prod à J-21 de la course).
    """
    raw = race.get("prep_start_date")
    if raw:
        anchor = date.fromisoformat(raw)
    else:
        anchor = today
        db.table("race_goals").update({"prep_start_date": today.isoformat()}).eq(
            "id", race["id"]
        ).execute()
    # Jamais dans le futur (course re-datée à la main), jamais au-delà de la
    # contrainte DB sur weeks_count.
    anchor = min(anchor, today)
    return max(anchor, race_date - timedelta(weeks=_MAX_PREP_WEEKS))


def _realign_past_week_offsets(db: Any, *, plan_id: str, grid_start: date, today_iso: str) -> None:
    """Réaligne les week_offset des séances passées re-parentées (#123 corollaire).

    Les sessions héritées d'anciens plans portaient les offsets de LEUR grille
    d'origine -> deux « semaine 0 » coexistaient dans un même plan et l'affichage
    « semaine N » du frontend était faux. On regroupe par offset recalculé pour
    limiter le nombre d'updates (une par semaine passée, pas une par séance).
    """
    rows = cast(
        DbRows,
        db.table("planned_sessions")
        .select("id, date")
        .eq("plan_id", plan_id)
        .lt("date", today_iso)
        .execute()
        .data
        or [],
    )
    by_offset: dict[int, list[str]] = {}
    for row in rows:
        offset = max(0, (date.fromisoformat(row["date"]) - grid_start).days // 7)
        by_offset.setdefault(offset, []).append(row["id"])
    for offset, ids in by_offset.items():
        db.table("planned_sessions").update({"week_offset": offset}).in_("id", ids).execute()


def generate_plan(user_id: str, *, today: date | None = None) -> dict[str, Any]:
    """Generate a training plan for the given user.

    ``today`` est injectable pour tester la stabilité des régénérations (l'ancre
    de périodisation ne bouge pas quand `today` avance).

    Returns:
        {"status": "ok", "plan_id": str, "weeks_count": int, "sessions_count": int}
        {"status": "no_race_goal"} if user has no active race
        {"status": "no_profile"} if profile not found
        {"status": "race_in_past"} if race_date already past
    """
    db = get_admin_client()

    profile = cast(
        "dict[str, Any] | None",
        db.table("athlete_profiles")
        # vma_kmh / css_per_100m_s ne servent pas au budget de charge : ils donnent
        # au jour J des allures cibles mesurées plutôt que des vitesses de référence.
        .select(
            "user_id, hours_per_week, ftp_watts, fc_max_bpm, sports_strengths, "
            "available_days, vma_kmh, css_per_100m_s"
        )
        .eq("user_id", user_id)
        .single()
        .execute()
        .data,
    )
    if not profile:
        return {"status": "no_profile"}

    _race_builder = (
        db.table("race_goals")
        .select("id, race_date, discipline, legs, prep_start_date")
        .eq("user_id", user_id)
        .eq("is_primary", True)
        .maybe_single()
    )
    _race_executed = _race_builder.execute()
    race = cast("dict[str, Any] | None", _race_executed.data)  # type: ignore[union-attr]
    if not race:
        return {"status": "no_race_goal"}

    today = today or date.today()
    race_date = date.fromisoformat(race["race_date"])
    if race_date <= today:
        return {"status": "race_in_past"}

    tss_by_date, today_state, activity_review, activities = _load_today_banister_state(
        db=db, user_id=user_id, profile=profile, today=today
    )
    first_week_tss_multiplier = compute_first_week_tss_multiplier(activity_review)

    # Phases ancrées sur le début de préparation immuable, pas sur `today` :
    # la régénération hebdo recalcule les charges, plus jamais le découpage.
    anchor = _ensure_prep_anchor(db, race, today=today, race_date=race_date)
    phases = compute_phases(anchor, race_date)
    weeks_count = len(phases)
    # Dédupliqué en préservant l'ordre : un duathlon run-bike-run ne doit pas
    # peser la course deux fois dans la rotation (les parts de temps s'en
    # chargent via estimate_race_time_shares).
    sports_in_race = list(dict.fromkeys(leg["discipline"] for leg in race["legs"]))
    race_time_shares = estimate_race_time_shares(race["legs"])
    race_sport = _race_day_sport(race)
    sports_strengths = profile.get("sports_strengths") or {"swim": 3, "bike": 3, "run": 3}
    effective_strengths = load_effective_strengths(
        db, user_id, sports_strengths, today=today, activities=activities
    )
    available_days = profile.get("available_days") or ["mon", "wed", "fri"]

    # Per-sport race D+ — la cible hebdo est dérivée par semaine (progression
    # ancrée) dans _build_all_week_sessions, en partant du D+ observé.
    race_dplus_by_sport = compute_elevation_per_sport(race.get("legs") or [])
    observed_weekly_dplus = observed_weekly_elevation_by_sport(activities, today=today)
    observed_weekday_counts, observed_weekday_durations = observed_weekday_usage(
        activities, today=today
    )

    # Anchor the week grid so the LAST week ENDS on race_date (race day = last day
    # of the last week). Previously week_start was pinned to the Monday of the
    # current week while phases were counted from ``today`` — the two origins
    # diverged, leaving the plan ending up to 13 days before the race with no
    # taper and no race session (prod bug 2026-07). Days before ``today`` (when the
    # grid starts slightly in the past) are dropped just before insert.
    week_start = race_date - timedelta(days=weeks_count * 7 - 1)
    # Avec l'ancre, la semaine « courante » n'est plus forcément l'offset 0 : le
    # multiplicateur prudent de reprise s'applique à la première semaine générée.
    current_offset = min(weeks_count - 1, max(0, (today - week_start).days // 7))
    all_sessions = _build_all_week_sessions(
        phases=phases,
        today_state=today_state,
        profile=profile,
        first_week_tss_multiplier=first_week_tss_multiplier,
        current_offset=current_offset,
        sports_in_race=sports_in_race,
        effective_strengths=effective_strengths,
        available_days=available_days,
        weeks_count=weeks_count,
        week_start=week_start,
        race=RaceTarget(
            day=race_date,
            sport=race_sport,
            time_shares=race_time_shares,
            dplus_by_sport=race_dplus_by_sport,
            has_bike_run_transition=race_has_bike_run_transition(race.get("legs") or []),
            legs=race.get("legs") or [],
            # Niveaux EFFECTIFS (historique 90 j), pas déclarés : le temps estimé
            # du jour J doit refléter l'athlète tel qu'il s'entraîne réellement.
            athlete={**profile, "sports_strengths": effective_strengths},
        ),
        observed=ObservedHabits(
            weekday_counts=observed_weekday_counts,
            weekday_durations=observed_weekday_durations,
            weekly_dplus=observed_weekly_dplus,
        ),
    )

    # Drop any session dated before today: when the week grid starts a few days in
    # the past (race offset not a whole number of weeks), those days are already
    # gone and would only ever show up as empty, never-generated sessions.
    today_iso = today.isoformat()
    all_sessions = [s for s in all_sessions if s["date"] >= today_iso]

    # Reuse workouts already generated (and already billed) for identical upcoming
    # sessions, instead of re-paying the LLM for the same generations every week.
    existing_future_resp = (
        db.table("planned_sessions")
        .select("date, sport, session_type, target_duration_s, workout, workout_generated_at")
        .eq("user_id", user_id)
        .gte("date", today_iso)
        .execute()
    )
    reused_workouts = carry_over_workouts(
        all_sessions, cast(DbRows, existing_future_resp.data or [])
    )

    # Écart budget déclaré / planifié rendu visible (#129) : l'UI peut afficher
    # « X h planifiées sur Y h déclarées » au lieu de laisser l'athlète deviner
    # pourquoi son plan ne remplit pas son budget. Semaine de référence = la
    # première semaine entièrement future (la semaine courante peut être amputée).
    reference_offset = min(current_offset + 1, weeks_count - 1)
    planned_seconds = sum(
        s.get("target_duration_s") or 0
        for s in all_sessions
        if s["week_offset"] == reference_offset
    )
    planned_hours_reference_week = round(planned_seconds / 3600, 1)

    # Archive ALL of the user's plans, not just this race's: scoping the cleanup to
    # race_goal_id left an orphan ACTIVE plan (and duplicate sessions on /today)
    # whenever the primary race changed.
    previous_plans_resp = db.table("training_plans").select("id").eq("user_id", user_id).execute()
    previous_plan_ids = [p["id"] for p in cast(DbRows, previous_plans_resp.data or [])]
    if previous_plan_ids:
        # Only FUTURE sessions are replaced. Past sessions are the athlete's history
        # (prévu/réalisé) and are re-parented to the new plan further down — the
        # unfiltered delete used to wipe every past session on each weekly run.
        db.table("planned_sessions").delete().in_("plan_id", previous_plan_ids).gte(
            "date", today_iso
        ).execute()
        db.table("training_plans").update({"status": "archived"}).in_(
            "id", previous_plan_ids
        ).execute()

    # Insert new plan
    insert_resp = (
        db.table("training_plans")
        .insert(
            {
                "user_id": user_id,
                "race_goal_id": race["id"],
                # start_date = ancre de prep : cohérent avec weeks_count/end_date
                # (les week_offset se lisent depuis cette origine).
                "start_date": anchor.isoformat(),
                "end_date": race_date.isoformat(),
                "weeks_count": weeks_count,
                "ctl_initial": round(today_state.ctl, 2),
                "atl_initial": round(today_state.atl, 2),
                "tsb_initial": round(today_state.tsb, 2),
                "status": "active",
                "params": {
                    "cold_start": is_cold_start(tss_by_date),
                    "first_week_tss_multiplier": first_week_tss_multiplier,
                    "activity_review_signals": [i.name for i in activity_review.insights],
                    "prep_start_date": anchor.isoformat(),
                    "current_week_offset": current_offset,
                    "declared_hours_per_week": profile.get("hours_per_week"),
                    "planned_hours_reference_week": planned_hours_reference_week,
                },
            }
        )
        .execute()
    )
    plan_id = cast(DbRows, insert_resp.data)[0]["id"]

    if previous_plan_ids:
        # Re-parent past sessions to the new plan so the athlete keeps their history:
        # the app reads planned_sessions through an INNER JOIN on the ACTIVE plan, so
        # anything left on an archived plan silently disappears from /plan and /stats.
        db.table("planned_sessions").update({"plan_id": plan_id}).in_(
            "plan_id", previous_plan_ids
        ).lt("date", today_iso).execute()
        # ... et réaligner leurs week_offset sur la grille ancrée (sinon deux
        # « semaine 0 » coexistent dans le plan, cf. bug prod du 13/07 + 26/07).
        _realign_past_week_offsets(db, plan_id=plan_id, grid_start=week_start, today_iso=today_iso)

    for s in all_sessions:
        s["plan_id"] = plan_id
        s["user_id"] = user_id
    if all_sessions:
        db.table("planned_sessions").insert(all_sessions).execute()

    return {
        "status": "ok",
        "plan_id": plan_id,
        "weeks_count": weeks_count,
        "sessions_count": len(all_sessions),
        "reused_workouts": reused_workouts,
    }
