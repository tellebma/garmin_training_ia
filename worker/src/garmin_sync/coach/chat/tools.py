"""Catalogue d'outils exposés au LLM du chat coach (E11).

Principe : le modèle ne reçoit aucune métrique dans son prompt. Il demande les
données dont il a besoin via ces outils, qui lisent la base et ne renvoient que
des agrégats bornés.

Trois règles de conception, dans l'ordre d'importance :

1. **Aucun outil n'expose ``user_id`` dans son schéma JSON.** Le worker parle à
   Supabase en service role, donc RLS est court-circuité : si le modèle pouvait
   choisir le ``user_id``, une question bien tournée suffirait à lire les données
   d'un autre athlète. Le ``user_id`` est injecté par :func:`execute_tool` depuis
   le JWT vérifié, hors de portée du modèle.
2. **Les plafonds sont appliqués côté serveur**, jamais dans le prompt. Si le
   modèle demande ``limit=5000``, il reçoit 30 lignes — c'est le serveur qui
   décide.
3. **Aucun outil ne renvoie de lignes brutes volumineuses** (samples GPS,
   polyline) ni de données hors sujet (coordonnées du domicile). Ce qui n'est pas
   nécessaire à une réponse d'entraînement ne sort pas de la base.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from garmin_sync.coach.chat.handlers import (
    _SPORTS,
    MAX_ACTIVITIES,
    MAX_FEEDBACK,
    MAX_FORM_DAYS,
    MAX_HISTORY_DAYS,
    MAX_PROFILE_BUCKETS,
    ToolError,
    _get_activity_detail,
    _get_activity_feedback,
    _get_athlete_profile,
    _get_form_state,
    _get_planned_sessions,
    _get_race_goal,
    _get_recent_activities,
    _get_recovery_state,
)
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

__all__ = ["TOOLS", "Tool", "ToolError", "execute_tool", "openai_tool_specs"]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]


# --- Catalogue --------------------------------------------------------------

TOOLS: dict[str, Tool] = {
    "get_athlete_profile": Tool(
        name="get_athlete_profile",
        description=(
            "Profil sportif de l'athlète : âge, sexe, FTP vélo, VMA course, FC max, "
            "CSS natation, heures disponibles par semaine, niveau par discipline. "
            "Appelle-le quand la réponse dépend du niveau ou des zones physiologiques."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_get_athlete_profile,
    ),
    "get_form_state": Tool(
        name="get_form_state",
        description=(
            "État de forme calculé par le modèle de Banister : CTL (forme), ATL (fatigue), "
            "TSB (fraîcheur) et TSS quotidien, jour par jour. Indispensable pour toute "
            "question sur la fatigue, l'affûtage ou la préparation d'une course."
        ),
        parameters={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": (
                        f"Profondeur d'historique en jours (1-{MAX_FORM_DAYS}, défaut 30)."
                    ),
                }
            },
            "additionalProperties": False,
        },
        handler=_get_form_state,
    ),
    "get_recovery_state": Tool(
        name="get_recovery_state",
        description=(
            "Récupération : baselines HRV, FC de repos, sommeil, stress et Body Battery, "
            "plus les 7 derniers jours de mesures. À utiliser pour juger si l'athlète est "
            "reposé, ou pour expliquer une sensation de fatigue."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_get_recovery_state,
    ),
    "get_recent_activities": Tool(
        name="get_recent_activities",
        description=(
            "Séances réalisées, agrégées (durée, distance, dénivelé, FC, TSS). Renvoie un "
            "id par activité, réutilisable avec get_activity_detail. Ne renvoie jamais le "
            "tracé GPS."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sport": {
                    "type": "string",
                    "enum": list(_SPORTS),
                    "description": "Filtre par discipline. Omettre pour toutes.",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Nombre d'activités (1-{MAX_ACTIVITIES}, défaut 15).",
                },
                "days": {
                    "type": "integer",
                    "description": f"Fenêtre en jours (1-{MAX_HISTORY_DAYS}, défaut 90).",
                },
            },
            "additionalProperties": False,
        },
        handler=_get_recent_activities,
    ),
    "get_activity_detail": Tool(
        name="get_activity_detail",
        description=(
            "Analyse fine d'UNE activité : profil découpé en tranches avec altitude, "
            "fréquence cardiaque et vitesse moyennes. Permet de répondre à « où ai-je "
            "faibli dans la montée » ou « comment ai-je géré mon effort ». Requiert un id "
            "obtenu via get_recent_activities."
        ),
        parameters={
            "type": "object",
            "properties": {
                "activity_id": {"type": "string", "description": "Identifiant de l'activité."},
                "buckets": {
                    "type": "integer",
                    "description": f"Nombre de tranches (4-{MAX_PROFILE_BUCKETS}, défaut 20).",
                },
            },
            "required": ["activity_id"],
            "additionalProperties": False,
        },
        handler=_get_activity_detail,
    ),
    "get_planned_sessions": Tool(
        name="get_planned_sessions",
        description=(
            "Séances planifiées par le moteur de périodisation sur une plage de dates "
            "(sport, type, durée cible, TSS cible, phase). Défaut : aujourd'hui à J+14."
        ),
        parameters={
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "Date de début (AAAA-MM-JJ)."},
                "to_date": {"type": "string", "description": "Date de fin (AAAA-MM-JJ)."},
            },
            "additionalProperties": False,
        },
        handler=_get_planned_sessions,
    ),
    "get_race_goal": Tool(
        name="get_race_goal",
        description=(
            "Courses objectifs : date, discipline, distances et dénivelé par segment, "
            "temps visé, nombre de jours restants."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_get_race_goal,
    ),
    "get_activity_feedback": Tool(
        name="get_activity_feedback",
        description=(
            "Ressentis déclarés après séance : RPE, fatigue, courbatures, douleurs "
            "(et zone), humeur, difficulté perçue. Complète les données de la montre par "
            "le vécu de l'athlète."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": f"Nombre de retours (1-{MAX_FEEDBACK}, défaut 10).",
                }
            },
            "additionalProperties": False,
        },
        handler=_get_activity_feedback,
    ),
}


def openai_tool_specs() -> list[dict[str, Any]]:
    """Schémas d'outils au format attendu par l'API OpenAI."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in TOOLS.values()
    ]


def execute_tool(name: str, arguments: dict[str, Any], *, user_id: str) -> Any:
    """Exécute un outil pour le compte de ``user_id``.

    ``user_id`` est un paramètre nommé du worker, jamais une clé de
    ``arguments`` : même si le modèle en fabrique un, il est écarté ici. C'est la
    seule barrière entre un LLM et une base interrogée en service role.
    """
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Outil inconnu : {name}")

    allowed = tool.parameters["properties"]
    safe_args = {k: v for k, v in (arguments or {}).items() if k in allowed}
    dropped = set((arguments or {}).keys()) - set(safe_args.keys())
    if dropped:
        # Trace volontaire : un modèle qui tente de passer user_id doit se voir.
        log.warning("chat tool %s: arguments ignorés %s", name, sorted(dropped))

    # Un paramètre requis absent doit revenir au modèle comme une erreur qu'il
    # peut corriger au tour suivant, pas remonter en TypeError (donc en 500).
    missing = [k for k in tool.parameters.get("required", []) if k not in safe_args]
    if missing:
        raise ToolError(f"Paramètre(s) manquant(s) pour {name} : {', '.join(missing)}")

    return tool.handler(get_admin_client(), user_id, **safe_args)
