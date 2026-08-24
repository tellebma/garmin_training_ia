"""Décomposition d'une activité multisport Garmin en segments par discipline.

Garmin expose un triathlon (ou duathlon / aquathlon) comme une activité *parent*
agrégée qui référence des activités *enfants*, une par discipline, plus les
transitions. Le parent seul ne dit rien d'exploitable — sa distance additionne
1,5 km de nage et 40 km de vélo, son allure moyenne ne veut rien dire.

Ce module extrait les identifiants des enfants puis transforme chaque enfant en
une ligne `activity_segments`. Aucune ligne `activities` n'est créée pour les
enfants : la charge (TSS) reste portée par le parent, donc pas de double comptage.

La forme des payloads Garmin varie selon les endpoints et les versions — les
extracteurs ci-dessous acceptent donc plusieurs emplacements pour la même donnée
plutôt que de supposer une seule forme.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from garmin_sync.transformers.activities import normalize_sport

# Emplacements connus de la liste des activités enfants dans le résumé d'un parent.
_CHILD_ID_PATHS: tuple[tuple[str, ...], ...] = (
    ("metadataDTO", "childIds"),
    ("metadataDTO", "childActivityIds"),
    ("childIds",),
    ("childActivityIds",),
)

# Résumé des métriques : à la racine (liste d'activités) ou sous `summaryDTO`
# (détail d'une activité).
_SUMMARY_KEYS = ("summaryDTO", "activitySummary")

_TRANSITION_SPORTS = {"transition", "multisport_transition", "swim_to_bike_transition"}


def _summary(raw: dict[str, Any]) -> dict[str, Any]:
    """Métriques de l'activité, que Garmin les mette à plat ou sous `summaryDTO`."""
    merged: dict[str, Any] = {k: v for k, v in raw.items() if not isinstance(v, dict)}
    for key in _SUMMARY_KEYS:
        summary = raw.get(key)
        if isinstance(summary, dict):
            merged = {**merged, **summary}
    return merged


def _type_key(raw: dict[str, Any]) -> str:
    for key in ("activityTypeDTO", "activityType"):
        node = raw.get(key)
        if isinstance(node, dict):
            type_key = node.get("typeKey")
            if isinstance(type_key, str):
                return type_key
    type_key = raw.get("activityType")
    return type_key if isinstance(type_key, str) else "unknown"


def normalize_segment_sport(raw_sport: str) -> str:
    """Discipline d'un segment.

    Diffère de `normalize_sport` sur un point : une transition reste une
    « transition ». Au niveau de l'activité entière elle vaut `brick`, mais dans
    une décomposition c'est justement le segment qu'il faut distinguer des trois
    disciplines.
    """
    if raw_sport in _TRANSITION_SPORTS:
        return "transition"
    return normalize_sport(raw_sport)


def extract_child_activity_ids(summary: dict[str, Any]) -> list[int]:
    """Identifiants des activités enfants d'un multisport, dans l'ordre de l'épreuve.

    Renvoie une liste vide si le payload n'en porte pas — cas normal pour une
    activité simple, et cas dégradé accepté pour un multisport dont Garmin ne
    publie pas la décomposition.
    """
    for path in _CHILD_ID_PATHS:
        node: Any = summary
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, list):
            ids = [_to_int(item) for item in node]
            found = [value for value in ids if value is not None and value > 0]
            if found:
                return found
    return []


def transform_activity_segment(
    *,
    user_id: str,
    parent_activity_id: int,
    segment_index: int,
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Convertit une activité enfant Garmin en ligne `activity_segments`."""
    summary = _summary(raw)
    duration_s = _to_int(_first(summary, ("duration", "elapsedDuration", "movingDuration")))
    distance_m = _to_float(summary.get("distance"))
    speed_m_s = _to_float(_first(summary, ("averageSpeed", "avgSpeed")))
    return {
        "user_id": user_id,
        "garmin_activity_id": parent_activity_id,
        "segment_index": segment_index,
        "sport": normalize_segment_sport(_type_key(raw)),
        "garmin_child_activity_id": _to_int(_first(raw, ("activityId",)))
        or _to_int(summary.get("activityId")),
        "start_time": _parse_start(summary),
        "duration_s": duration_s,
        "distance_m": distance_m,
        "elevation_gain_m": _to_int(summary.get("elevationGain")),
        "hr_avg": _to_int(_first(summary, ("averageHR", "avgHr"))),
        "pace_avg_s_per_km": _pace_s_per_km(speed_m_s, distance_m, duration_s),
    }


def _pace_s_per_km(
    speed_m_s: float | None, distance_m: float | None, duration_s: int | None
) -> float | None:
    """Allure en s/km, depuis la vitesse moyenne ou, à défaut, distance / durée."""
    if speed_m_s and speed_m_s > 0:
        return round(1000.0 / speed_m_s, 2)
    if distance_m and distance_m > 0 and duration_s and duration_s > 0:
        return round(duration_s / (distance_m / 1000.0), 2)
    return None


_START_KEYS = ("startTimeGMT", "startTimeLocal")


def _parse_start(summary: dict[str, Any]) -> str | None:
    for key in _START_KEYS:
        value = summary.get(key)
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        return parsed.isoformat()
    return None


def _first(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
