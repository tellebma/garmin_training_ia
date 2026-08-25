"""Portée des activités qui comptent (E24).

Une activité peut être **exclue** par l'athlète — cas vécu : compteur vélo lancé en
plus de la montre le jour de la course, donc deux lignes pour un seul effort. Une
activité exclue ne doit plus peser sur la charge, les volumes, le coach ni la vue
course.

Le risque de cette règle n'est pas de poser le filtre : c'est de l'oublier au
prochain écran. D'où **un seul point d'entrée**, greppable : toute lecture qui
alimente une métrique passe par ``counted()``.

Ne l'utilisent volontairement PAS :

- ``sync`` : ingestion, samples, GPS et décomposition multisport continuent de tourner
  sur une activité exclue — une restauration doit retrouver une activité intacte ;
- ``dedup`` : une activité exclue reste la preuve que l'effort existe déjà côté Garmin ;
- ``backfill_tss`` : recalculer le TSS d'une ligne exclue n'affecte aucun agrégat et
  garde la donnée juste si elle est restaurée.
"""

from __future__ import annotations

from typing import Any


def counted(query: Any) -> Any:
    """Restreint une requête `activities` aux activités qui comptent."""
    return query.is_("excluded_at", "null")
