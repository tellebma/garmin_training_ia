"""Fenêtre de récupération après une course (E27.1).

La semaine qui suit une épreuve est une semaine de récupération — **quel que soit le cap
choisi ensuite**, y compris quand l'athlète enchaîne aussitôt sur un nouvel objectif. Un
plan qui repartirait à pleine charge le lendemain d'un half serait faux, même si c'est ce
que l'athlète demande.

Le barème est dérivé de la **durée réelle** de l'épreuve, pas de son format déclaré : un
« olympique » bouclé en 3 h 30 fatigue davantage qu'un sprint en 1 h 10, et c'est le temps
passé à l'effort qui décide de la récupération, pas l'étiquette de la course. Le format
déclaré ne sert que de repli quand aucune durée n'est exploitable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Barème par durée d'épreuve (secondes) -> jours de récupération.
_SHORT_RACE_S = 90 * 60
_LONG_RACE_S = 4 * 60 * 60

_SHORT_RECOVERY_DAYS = 3
_STANDARD_RECOVERY_DAYS = 7
_LONG_RECOVERY_DAYS = 14

# Repli quand la course n'a pas de durée exploitable (activité non rattachée, temps
# manquant) : le format déclaré est le seul signal restant.
_DAYS_BY_DISTANCE: dict[str, int] = {
    "sprint": _SHORT_RECOVERY_DAYS,
    "olympique": _STANDARD_RECOVERY_DAYS,
    "half_ironman": _LONG_RECOVERY_DAYS,
    "ironman": _LONG_RECOVERY_DAYS,
}

# Charge autorisée pendant la fenêtre, relative au budget habituel.
_FIRST_WEEK_MULTIPLIER = 0.5
_SECOND_WEEK_MULTIPLIER = 0.75

RECOVERY_SESSION_TYPES = ["recovery", "endurance"]
"""Aucune séance de qualité, aucune longue : on récupère, on ne s'entraîne pas."""


@dataclass(frozen=True)
class RecoveryWindow:
    """Fenêtre de récupération en cours, du lendemain de la course à ``end_date`` incluse."""

    race_date: date
    end_date: date
    total_days: int

    def covers(self, day: date) -> bool:
        return self.race_date < day <= self.end_date

    def load_multiplier(self, day: date) -> float:
        """0.5 la première semaine, 0.75 la seconde — 1.0 en dehors de la fenêtre."""
        if not self.covers(day):
            return 1.0
        days_elapsed = (day - self.race_date).days
        return _FIRST_WEEK_MULTIPLIER if days_elapsed <= 7 else _SECOND_WEEK_MULTIPLIER

    def _week_days(self, week_start: date) -> list[date]:
        return [week_start + timedelta(days=offset) for offset in range(7)]

    def covers_week(self, week_start: date) -> bool:
        """La fenêtre touche-t-elle cette semaine ?

        Tester le seul lundi laissait passer le cas le plus fréquent : une course
        courue en fin de semaine, dont la récupération commence le lendemain — la
        semaine en cours n'était alors pas considérée comme une semaine de récup,
        et l'athlète recevait une séance longue au lendemain de son épreuve.
        """
        return any(self.covers(day) for day in self._week_days(week_start))

    def week_load_multiplier(self, week_start: date) -> float:
        """Le multiplicateur le plus contraignant parmi les jours de la semaine.

        Une semaine à cheval sur la fin de la fenêtre reste allégée : on préfère une
        semaine trop douce à une semaine trop dure juste après une course.
        """
        return min(self.load_multiplier(day) for day in self._week_days(week_start))


def recovery_days(elapsed_s: float | None, race_distance: str | None = None) -> int:
    """Jours de récupération dus après une épreuve de cette durée."""
    if elapsed_s is not None and elapsed_s > 0:
        if elapsed_s < _SHORT_RACE_S:
            return _SHORT_RECOVERY_DAYS
        if elapsed_s <= _LONG_RACE_S:
            return _STANDARD_RECOVERY_DAYS
        return _LONG_RECOVERY_DAYS
    # Sans durée : le format déclaré, et à défaut le barème médian — ne rien prévoir
    # serait le seul choix franchement mauvais.
    return _DAYS_BY_DISTANCE.get(race_distance or "", _STANDARD_RECOVERY_DAYS)


def post_race_recovery(
    *,
    race_date: date | None,
    elapsed_s: float | None,
    today: date,
    race_distance: str | None = None,
) -> RecoveryWindow | None:
    """Fenêtre de récupération encore en cours aujourd'hui, ou ``None``.

    ``None`` couvre les trois cas où il n'y a rien à imposer : pas de course connue,
    course encore à venir, fenêtre déjà terminée.
    """
    if race_date is None or race_date > today:
        return None
    days = recovery_days(elapsed_s, race_distance)
    end_date = race_date + timedelta(days=days)
    if today > end_date:
        return None
    return RecoveryWindow(race_date=race_date, end_date=end_date, total_days=days)
