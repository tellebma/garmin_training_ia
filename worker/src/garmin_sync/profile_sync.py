"""Garmin profile auto-fetch — pulls FTP/VO2max/FCmax from Garmin Connect and
upserts into athlete_profiles. Called from the wizard step Perf and from the
'↻ Sync Garmin' button on /profile.

Design notes
------------
- We NEVER touch dob/sex (saisis manuellement à l'étape Perso, overwrite serait
  surprenant UX).
- We exclude keys whose Garmin value is None — the resulting UPDATE only writes
  fields where Garmin has a fresh value, preserving any manual entry the user
  made before.
- No cooldown : tokens already valid, the endpoint never triggers the login
  cascade that PR #6 protects against.
"""

from __future__ import annotations

from typing import Any


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _vma_from_vo2max(vo2: float | None) -> float | None:
    """VO2max (ml/kg/min) → VMA (km/h) via VMA = VO2max / 3.5 (formule classique)."""
    if not vo2:
        return None
    return round(vo2 / 3.5, 2)


def _normalize_sex(raw: str | None) -> str | None:
    if not raw:
        return None
    upper = raw.upper()
    if upper == "MALE":
        return "M"
    if upper == "FEMALE":
        return "F"
    if upper == "OTHER":
        return "X"
    return None


def _transform_profile(user_profile: dict[str, Any], max_metrics: dict[str, Any]) -> dict[str, Any]:
    """Return only non-null perf fields. Keys with None values are EXCLUDED."""
    row: dict[str, Any] = {}
    ftp = _safe_int(user_profile.get("functionalThresholdPower"))
    if ftp is not None:
        row["ftp_watts"] = ftp
    vma = _vma_from_vo2max(max_metrics.get("vo2MaxValueRunning"))
    if vma is not None:
        row["vma_kmh"] = vma
    fcmax = _safe_int(user_profile.get("userMaxHr"))
    if fcmax is not None:
        row["fc_max_bpm"] = fcmax
    return row
