"""Cross the declared per-discipline level with the real 90-day history (E13.2).

Pure module, no DB access. Derives an observed-level signal per discipline from
activity volume, regularity and sustained load, reconciles it with the declared
level into a bounded effective level (+/-1 max), and explains the divergence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from garmin_sync.coach.sports import CORE_DISCIPLINES, contributing_disciplines

WINDOW_DAYS = 90
MIN_ACTIVITIES_CONFIDENT = 6
STRONG_REGULARITY = 2.0  # sessions/week to justify a level-up
WEAK_REGULARITY = 0.5  # sessions/week below which a declared-strong level drops
_SUBWINDOW_DAYS = 30
_LEVEL_MIN = 1
_LEVEL_MAX = 5
_DEFAULT_LEVEL = 3
_LABELS = {"swim": "Natation", "bike": "Vélo", "run": "Course"}


@dataclass(frozen=True)
class DisciplineLevel:
    declared: int
    effective: int
    adjustment: int
    confidence: str  # "high" | "low"
    reason: str
    signals: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "declared": self.declared,
            "effective": self.effective,
            "adjustment": self.adjustment,
            "confidence": self.confidence,
            "reason": self.reason,
            "signals": self.signals,
        }


@dataclass(frozen=True)
class DisciplineLevels:
    disciplines: dict[str, DisciplineLevel]

    @property
    def effective_strengths(self) -> dict[str, int]:
        return {k: v.effective for k, v in self.disciplines.items()}

    def to_dict(self) -> dict[str, Any]:
        return {"disciplines": {k: v.to_dict() for k, v in self.disciplines.items()}}


def _activity_date(row: dict[str, Any]) -> date | None:
    raw = row.get("start_time")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _activity_tss(row: dict[str, Any]) -> float:
    raw_tss = row.get("tss")
    if raw_tss is not None:
        return float(raw_tss)
    duration_s = row.get("duration_s") or 0
    return max(0.0, float(duration_s) / 3600 * 50)


def _group_by_discipline(
    activities: list[dict[str, Any]], today: date
) -> tuple[dict[str, list[tuple[date, float]]], float]:
    """Bucket in-window activities per discipline, plus the total TSS.

    A brick feeds BOTH the bike and the run bucket (#169) — it genuinely trains
    the two. The total is therefore accumulated separately, so that an activity
    landing in two buckets is still counted once in the athlete's overall load
    and does not dilute every ``tss_share``.
    """
    start = today - timedelta(days=WINDOW_DAYS)
    grouped: dict[str, list[tuple[date, float]]] = {}
    total_tss = 0.0
    for row in activities:
        d = _activity_date(row)
        if d is None or not (start <= d <= today):
            continue
        disciplines = contributing_disciplines(str(row.get("sport") or ""))
        if not disciplines:
            continue
        tss = _activity_tss(row)
        total_tss += tss
        for disc in disciplines:
            grouped.setdefault(disc, []).append((d, tss))
    return grouped, total_tss


def _signals(entries: list[tuple[date, float]], total_tss: float, today: date) -> dict[str, Any]:
    n = len(entries)
    sessions_per_week = round(n / (WINDOW_DAYS / 7), 2)
    buckets = {min((today - d).days // _SUBWINDOW_DAYS, 2) for d, _t in entries}
    sustained = len(buckets) >= 2
    disc_tss = sum(t for _d, t in entries)
    tss_share = round(disc_tss / total_tss, 2) if total_tss > 0 else 0.0
    return {
        "activities_90d": n,
        "sessions_per_week": sessions_per_week,
        "sustained": sustained,
        "tss_share": tss_share,
    }


def _reconcile(discipline: str, declared: int, signals: dict[str, Any]) -> DisciplineLevel:
    label = _LABELS.get(discipline, discipline)
    spw = float(signals["sessions_per_week"])
    sustained = bool(signals["sustained"])
    confident = int(signals["activities_90d"]) >= MIN_ACTIVITIES_CONFIDENT

    if not confident:
        return DisciplineLevel(
            declared, declared, 0, "low", "Données insuffisantes pour confirmer.", signals
        )

    if declared <= 2 and spw >= STRONG_REGULARITY and sustained:
        effective = min(_LEVEL_MAX, declared + 1)
        if effective != declared:
            reason = (
                f"{label} remonté à {effective} : entraînement régulier et soutenu "
                f"(~{spw}/sem sur 90 j) au-dessus du niveau déclaré."
            )
            return DisciplineLevel(declared, effective, 1, "high", reason, signals)

    if declared >= 4 and spw <= WEAK_REGULARITY:
        effective = max(_LEVEL_MIN, declared - 1)
        if effective != declared:
            reason = (
                f"{label} ajusté à {effective} : peu d'entraînement observé sur 90 j "
                f"malgré un niveau déclaré élevé."
            )
            return DisciplineLevel(declared, effective, -1, "high", reason, signals)

    return DisciplineLevel(declared, declared, 0, "high", "Niveau confirmé.", signals)


def compute_discipline_levels(
    declared: dict[str, int],
    activities: list[dict[str, Any]],
    today: date | None = None,
) -> DisciplineLevels:
    today = today or date.today()
    grouped, total_tss = _group_by_discipline(activities, today)

    disciplines: dict[str, DisciplineLevel] = {}
    for disc in CORE_DISCIPLINES:
        decl = int(declared.get(disc, _DEFAULT_LEVEL))
        signals = _signals(grouped.get(disc, []), total_tss, today)
        disciplines[disc] = _reconcile(disc, decl, signals)
    return DisciplineLevels(disciplines=disciplines)


def load_effective_strengths(
    db: Any,
    user_id: str,
    declared: dict[str, int],
    today: date | None = None,
    activities: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Niveaux effectifs par discipline (déclaré reconcilié avec l'historique 90 j).

    ``activities`` peut être fourni par un appelant qui les a déjà chargées
    (ex. ``generate_plan``) pour éviter une requête redondante ; sinon on charge
    les 90 derniers jours pour ``user_id``.
    """
    today = today or date.today()
    if activities is None:
        start = (today - timedelta(days=WINDOW_DAYS)).isoformat()
        resp = (
            db.table("activities")
            .select("start_time, sport, duration_s, tss")
            .eq("user_id", user_id)
            .gte("start_time", start)
            .execute()
        )
        activities = list(resp.data or [])
    return compute_discipline_levels(declared, activities, today=today).effective_strengths
