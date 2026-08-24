"""Détection des activités de course et rattachement à leur `race_goal` (E23.1).

Une course n'existait qu'avant l'épreuve : l'activité du jour J retombait ensuite
dans l'historique comme une sortie ordinaire. Ce module rattache l'activité à la
course qu'elle réalise, ce qui débloque la vue course, le débrief et la lecture de
progression d'une épreuve à l'autre.

Tout est DÉTERMINISTE : un rattachement doit être reproductible et explicable, et
une erreur de tag se paie cher (une course fantôme dans les progressions). Trois
conditions cumulatives, et rien d'autre :

1. **date** — l'activité démarre le jour de la course ;
2. **discipline** — le sport de l'activité est cohérent avec les `legs` de l'épreuve
   (ou est un sport multisport agrégé pour une course à transitions) ;
3. **volume plausible** — la distance couvre au moins 60 % de la distance attendue,
   ou, sans distance exploitable, l'activité dure au moins 20 minutes.

La troisième condition écarte le faux positif le plus probable : le décrassage ou la
reconnaissance de parcours faits le matin même de la course.

Une activité taguée à la main (`race_tag_source = 'manual'`) n'est jamais réécrite :
dé-taguer un footing pris à tort pour une course doit tenir dans le temps.
"""

from __future__ import annotations

import logging
from typing import Any, cast

log = logging.getLogger(__name__)

# Part de la distance attendue en dessous de laquelle l'activité n'est pas la course.
MIN_DISTANCE_RATIO = 0.6
# Sans distance exploitable (natation en piscine mal mesurée, GPS absent), on retombe
# sur une durée plancher : un décrassage de 20 min n'est pas une épreuve.
MIN_DURATION_S = 20 * 60

# Sports d'une activité multisport agrégée (parent Garmin d'un triathlon), alignés sur
# `sync._MULTISPORT_SPORTS` et sur les disciplines parentes de `planned_sessions`.
MULTISPORT_SPORTS: frozenset[str] = frozenset(
    {"brick", "multi_sport", "multisport", "triathlon", "duathlon", "aquathlon", "race"}
)

# Disciplines d'épreuve qui comportent des transitions : leur jour J peut arriver
# comme une seule activité multisport, ou comme une activité par discipline.
MULTI_LEG_DISCIPLINES: frozenset[str] = frozenset({"triathlon", "duathlon", "aquathlon"})

_LEG_SPORTS: frozenset[str] = frozenset({"swim", "bike", "run"})


def _legs(race: dict[str, Any]) -> list[dict[str, Any]]:
    legs = race.get("legs")
    if not isinstance(legs, list):
        return []
    return [leg for leg in legs if isinstance(leg, dict)]


def _leg_distance_m(leg: dict[str, Any]) -> float:
    try:
        return max(0.0, float(leg.get("distance_km") or 0.0)) * 1000.0
    except (TypeError, ValueError):
        return 0.0


def race_sports(race: dict[str, Any]) -> set[str]:
    """Disciplines acceptables pour une activité de cette course."""
    sports = {
        str(leg.get("discipline"))
        for leg in _legs(race)
        if str(leg.get("discipline")) in _LEG_SPORTS
    }
    discipline = str(race.get("discipline") or "")
    if discipline in _LEG_SPORTS:
        sports.add(discipline)
    if discipline in MULTI_LEG_DISCIPLINES or len(sports) > 1:
        sports |= MULTISPORT_SPORTS
    return sports


def expected_distance_m(race: dict[str, Any], sport: str) -> float:
    """Distance attendue pour une activité de ce sport sur cette course.

    Pour une activité multisport agrégée, c'est la distance totale de l'épreuve ;
    pour une activité mono-discipline, celle du (ou des) leg(s) de ce sport.
    """
    legs = _legs(race)
    total = sum(_leg_distance_m(leg) for leg in legs)
    if sport in MULTISPORT_SPORTS:
        if total > 0:
            return total
        return _total_distance_fallback(race)
    matching = sum(_leg_distance_m(leg) for leg in legs if str(leg.get("discipline")) == sport)
    if matching > 0:
        return matching
    # Course mono-discipline saisie sans legs : la distance totale fait foi.
    if total > 0:
        return total
    return _total_distance_fallback(race)


def _total_distance_fallback(race: dict[str, Any]) -> float:
    try:
        return max(0.0, float(race.get("total_distance_km") or 0.0)) * 1000.0
    except (TypeError, ValueError):
        return 0.0


def _activity_date(activity: dict[str, Any]) -> str:
    start = str(activity.get("start_time") or "")
    return start[:10]


def _is_plausible_volume(activity: dict[str, Any], race: dict[str, Any], sport: str) -> bool:
    expected = expected_distance_m(race, sport)
    distance = activity.get("distance_m")
    try:
        distance_m = float(distance) if distance is not None else 0.0
    except (TypeError, ValueError):
        distance_m = 0.0

    if expected > 0 and distance_m > 0:
        return distance_m >= expected * MIN_DISTANCE_RATIO

    try:
        duration_s = int(activity.get("duration_s") or 0)
    except (TypeError, ValueError):
        duration_s = 0
    return duration_s >= MIN_DURATION_S


def match_race_activities(
    races: list[dict[str, Any]],
    activities: list[dict[str, Any]],
) -> dict[str, str]:
    """Rattachements `{activity_id: race_goal_id}` à écrire.

    Fonction pure : ni I/O ni horloge. Les activités déjà taguées à la main sont
    ignorées, celles taguées automatiquement sur la bonne course aussi (rien à écrire).
    """
    by_date = _races_by_date(races)
    matches: dict[str, str] = {}
    for activity in activities:
        pair = _match_one(activity, by_date)
        if pair is not None:
            activity_id, race_id = pair
            matches[activity_id] = race_id
    return matches


def _races_by_date(races: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for race in races:
        race_date = str(race.get("race_date") or "")
        if race_date:
            by_date.setdefault(race_date, []).append(race)
    return by_date


def _match_one(
    activity: dict[str, Any],
    by_date: dict[str, list[dict[str, Any]]],
) -> tuple[str, str] | None:
    """Rattachement à écrire pour une activité, ou None s'il n'y a rien à faire."""
    if activity.get("race_tag_source") == "manual":
        return None
    candidates = by_date.get(_activity_date(activity))
    if not candidates:
        return None
    matched = _best_candidate(candidates, activity, str(activity.get("sport") or ""))
    if matched is None:
        return None
    activity_id = str(activity.get("id") or "")
    race_id = str(matched.get("id") or "")
    if not activity_id or not race_id or activity.get("race_goal_id") == race_id:
        return None
    return activity_id, race_id


def _best_candidate(
    candidates: list[dict[str, Any]],
    activity: dict[str, Any],
    sport: str,
) -> dict[str, Any] | None:
    """Course la plus exigeante en distance parmi celles que l'activité satisfait.

    Deux épreuves le même jour est un cas rare mais pas absurde (relais, format court
    puis format long) : à égalité de date et de discipline, on retient celle dont la
    distance attendue est la plus proche par le bas de la distance réalisée.
    """
    eligible = [
        race
        for race in candidates
        if sport in race_sports(race) and _is_plausible_volume(activity, race, sport)
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda race: expected_distance_m(race, sport))


def apply_race_tags(db: Any, user_id: str, matches: dict[str, str]) -> int:
    """Écrit les rattachements. Ne touche jamais une ligne `manual`."""
    written = 0
    for activity_id, race_goal_id in matches.items():
        try:
            (
                db.table("activities")
                .update({"race_goal_id": race_goal_id, "race_tag_source": "auto"})
                .eq("user_id", user_id)
                .eq("id", activity_id)
                .neq("race_tag_source", "manual")
                .execute()
            )
            written += 1
        except Exception:
            log.exception("race tag failed user=%s activity=%s", user_id, activity_id)
    return written


def tag_races_for_user(
    db: Any,
    user_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int:
    """Détecte et rattache les courses d'un athlète sur une fenêtre de dates.

    Sans bornes, couvre tout l'historique (mode backfill). Ne lève jamais : le tag est
    un enrichissement, il ne doit pas faire échouer le sync qui l'appelle.
    """
    try:
        races = _fetch_races(db, user_id, start_date, end_date)
        if not races:
            return 0
        activities = _fetch_activities(db, user_id, [str(r["race_date"]) for r in races])
        matches = match_race_activities(races, activities)
        return apply_race_tags(db, user_id, matches)
    except Exception:
        log.exception("race tagging failed user=%s", user_id)
        return 0


def _fetch_races(
    db: Any, user_id: str, start_date: str | None, end_date: str | None
) -> list[dict[str, Any]]:
    query = (
        db.table("race_goals")
        .select("id, race_date, discipline, legs, total_distance_km")
        .eq("user_id", user_id)
    )
    if start_date:
        query = query.gte("race_date", start_date)
    if end_date:
        query = query.lte("race_date", end_date)
    return cast("list[dict[str, Any]]", query.execute().data or [])


def _fetch_activities(db: Any, user_id: str, race_dates: list[str]) -> list[dict[str, Any]]:
    """Activités des jours de course uniquement — une requête bornée, pas l'historique."""
    if not race_dates:
        return []
    window_start = f"{min(race_dates)}T00:00:00Z"
    window_end = f"{max(race_dates)}T23:59:59Z"
    rows = cast(
        "list[dict[str, Any]]",
        (
            db.table("activities")
            .select("id, start_time, sport, distance_m, duration_s, race_goal_id, race_tag_source")
            .eq("user_id", user_id)
            .gte("start_time", window_start)
            .lte("start_time", window_end)
            .execute()
            .data
            or []
        ),
    )
    wanted = set(race_dates)
    return [row for row in rows if _activity_date(row) in wanted]
