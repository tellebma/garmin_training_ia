"""Banister model — exponential CTL/ATL/TSB tracking.

CTL ("Chronic Training Load") = long-term fitness, τ1 = 42 days.
ATL ("Acute Training Load") = short-term fatigue, τ2 = 7 days.
TSB ("Training Stress Balance") = CTL - ATL = "form" indicator.

Daily update :
    CTL_today = CTL_yesterday + (TSS_today - CTL_yesterday) / τ1
    ATL_today = ATL_yesterday + (TSS_today - ATL_yesterday) / τ2

Days without activity are treated as TSS=0 (decay).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

CTL_TAU = 42  # days — fitness time constant
ATL_TAU = 7  # days — fatigue time constant


@dataclass(frozen=True)
class BanisterState:
    """Banister state for a single day."""

    ctl: float
    atl: float
    tsb: float
    """Training stress balance, computed as ``ctl - atl``."""


def compute_banister_history(
    tss_by_date: dict[date, float],
    start: date,
    end: date,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> list[BanisterState]:
    """Iterate day-by-day from start to end inclusive. Returns list of states."""
    states: list[BanisterState] = []
    ctl, atl = initial_ctl, initial_atl
    current = start
    while current <= end:
        tss = tss_by_date.get(current, 0.0)
        ctl += (tss - ctl) / CTL_TAU
        atl += (tss - atl) / ATL_TAU
        states.append(BanisterState(ctl=ctl, atl=atl, tsb=ctl - atl))
        current += timedelta(days=1)
    return states


def estimate_initial_ctl_from_profile(hours_per_week: int | None) -> float:
    """Cold-start CTL estimate when no historical TSS available.

    Heuristic : weekly_TSS approx hours * 50 (endurance avg).
    Daily-equivalent baseline = weekly / 7.
    Returns 0.0 if hours_per_week is None or zero.
    """
    if not hours_per_week or hours_per_week <= 0:
        return 0.0
    weekly_tss = hours_per_week * 50
    return round(weekly_tss / 7, 2)
