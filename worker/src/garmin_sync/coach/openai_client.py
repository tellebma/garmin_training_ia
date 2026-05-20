"""Thin OpenAI client wrapper using structured outputs (Pydantic-typed responses)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from openai import OpenAI

from garmin_sync.coach.workout_schema import Workout
from garmin_sync.config import get_settings


class OpenAIError(Exception):
    """Raised when the OpenAI API call or response is unusable."""


_SYSTEM_PROMPT = """Tu es un coach triathlon expert. Tu produis des séances d'entraînement
structurées au format JSON strict suivant le schema fourni. Tu adaptes les cibles physiologiques
au profil de l'athlète. Tu réponds uniquement en JSON valide, sans aucun texte
en dehors du schema.

Règles :
- Échauffement : 10-15min, progression Z1->Z2.
- Retour calme : 8-12min, Z1.
- Séance "long" : un seul gros bloc continu (pas d'intervalles).
- Séance "intervals" : des sets répétés (work + rest).
- Séance "threshold" : 1-2 sets longs (>=8min work, 2-3min rest).
- Séance "recovery" : Z1 seulement, durée courte.
- Séance "endurance" : un seul bloc Z2-Z3 continu.
- summary_md : 1-2 phrases FR conseil du jour, motivant mais bref.
- technical_focus : 1 phrase FR sur l'aspect technique spécifique au sport.
"""


@lru_cache(maxsize=1)
def _get_client() -> OpenAI:
    s = get_settings()
    api_key = s.openai_api_key.get_secret_value()
    if not api_key:
        raise OpenAIError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key, timeout=s.openai_timeout_s)


def _build_user_prompt(
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_context: dict[str, Any],
) -> str:
    minutes = session["target_duration_s"] // 60
    sports = athlete.get("sports_strengths") or {}
    swim = sports.get("swim", "?")
    bike = sports.get("bike", "?")
    run = sports.get("run", "?")
    fc = athlete.get("fc_max_bpm")
    ftp = athlete.get("ftp_watts")
    vma = athlete.get("vma_kmh")

    target_dplus = session.get("target_elevation_gain_m")
    elevation_line = (
        f", dénivelé cible {target_dplus}m D+" if target_dplus and int(target_dplus) > 0 else ""
    )
    lines = [
        f"Session : {session['sport']} {session['session_type']} en phase {session['phase']}, "
        f"durée cible {minutes}min, TSS {session['target_tss']}{elevation_line}.",
        "",
        "Athlète :",
        f"- FC max : {fc} bpm" if fc else "- FC max : non connue",
    ]
    if session["sport"] == "bike":
        lines.append(f"- FTP : {ftp} W" if ftp else "- FTP : non connue")
    if session["sport"] == "run":
        lines.append(f"- VMA : {vma} km/h" if vma else "- VMA : non connue")
    lines.extend(
        [
            f"- Niveau (1-5) : swim={swim}, bike={bike}, run={run}",
            "",
            f"Course objectif (dans {race_context['weeks_to_race']} semaines) :",
            f"- Discipline : {race_context['discipline']}",
            f"- Dénivelé total : {race_context['total_elevation_gain_m']}m",
        ]
    )
    return "\n".join(lines)


def generate_workout_for_session(
    *,
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_context: dict[str, Any],
) -> Workout:
    """Call OpenAI with structured output, return a validated Workout."""
    client = _get_client()
    settings = get_settings()
    try:
        resp = client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(session, athlete, race_context)},
            ],
            response_format=Workout,
        )
    except Exception as e:
        raise OpenAIError(f"OpenAI call failed: {e}") from e
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        raise OpenAIError("OpenAI returned no parsed payload")
    return Workout.model_validate(parsed.model_dump())
