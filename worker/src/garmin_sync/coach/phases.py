"""Phase computation : backward planning from race_date.

Phase ratios (target distribution):
- base   : 50-60% of total weeks
- build  : 25-30%
- peak   : 10-15%
- taper  : last 1-2 weeks

For short plans (< 6 weeks), peak collapses into build.
For 1-week plans, the whole week is taper.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

Phase = Literal['base', 'build', 'peak', 'taper']


def compute_phases(start_date: date, race_date: date) -> list[tuple[int, Phase]]:
    """Return [(week_offset, phase), ...] from week 0 (start) to race week.

    Backward planning : taper at the end, then peak, then build, then base.
    """
    total_weeks = max(1, (race_date - start_date).days // 7)

    if total_weeks == 1:
        return [(0, 'taper')]

    # Targets — backward from race_date
    taper_weeks = 1 if total_weeks < 8 else 2
    peak_weeks = max(1, total_weeks // 8) if total_weeks >= 6 else 0
    build_weeks = max(2, total_weeks // 4) if total_weeks >= 6 else max(1, total_weeks // 3)
    base_weeks = max(0, total_weeks - taper_weeks - peak_weeks - build_weeks)

    phases: list[tuple[int, Phase]] = []
    for w in range(total_weeks):
        if w < base_weeks:
            phase: Phase = 'base'
        elif w < base_weeks + build_weeks:
            phase = 'build'
        elif w < total_weeks - taper_weeks:
            phase = 'peak'
        else:
            phase = 'taper'
        phases.append((w, phase))
    return phases
