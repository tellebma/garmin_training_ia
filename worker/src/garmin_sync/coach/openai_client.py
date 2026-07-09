"""Thin OpenAI client wrapper using structured outputs (Pydantic-typed responses)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import OpenAI

from garmin_sync.coach.workout_schema import (
    Workout,
    describe_session_envelope,
    validate_workout_for_session,
)
from garmin_sync.config import get_settings


@dataclass(frozen=True)
class LlmUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class WorkoutResult:
    workout: Workout
    usage: LlmUsage


class OpenAIError(Exception):
    """Raised when the OpenAI API call or response is unusable.

    ``raw_payload`` porte le JSON du workout rejeté par la validation, pour
    ré-injection en message assistant lors du retry correctif.
    """

    def __init__(self, message: str, raw_payload: str | None = None) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload


_SYSTEM_PROMPT = """Tu es un coach triathlon expert. Tu produis des séances d'entraînement
structurées au format JSON strict suivant le schema fourni. Tu adaptes les cibles physiologiques
au profil de l'athlète. Tu réponds uniquement en JSON valide, sans aucun texte
en dehors du schema.

Règles :
- Ne génère jamais de workout pour une séance "rest".
- La durée totale warmup + main + cooldown doit rester proche de la durée cible.
- Le corps de séance doit respecter la part minimale de la durée totale donnée dans
  les contraintes chiffrées de la demande.
- Échauffement et retour calme sont proportionnels : courts sur récupération/endurance courte,
  plus longs seulement pour seuil/PMA/sprint/intervalles.
- Évite les découpages artificiels type 45min avec 15min échauffement, 18min travail,
  12min retour calme.
- Séance "recovery" : Z1 seulement, durée courte, échauffement intégré ou minimal.
- Séance "endurance" : un bloc principal Z2-Z3 majoritaire.
- Séance "long" : un seul gros bloc continu (pas d'intervalles).
- Séance "intervals" : des sets répétés (work + rest).
- Séance "threshold" : 2-4 sets de 6-10min à intensité seuil (Z4), récupération 2-5min.
- Séance "pma" : répétitions de 1 à 3min à 110-130% du seuil (Z4-Z5), récupération
  égale au temps de travail — vise le plafond aérobie (VO2max).
- Séance "sprint" : répétitions très courtes de 5 à 15s à intensité maximale (Z5),
  récupération large (6 à 10 fois le temps de travail) — vise la force explosive et
  la vitesse de pointe, pas l'endurance.
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


def _athlete_lines(*, athlete: dict[str, Any], sport: str) -> list[str]:
    sports = athlete.get("sports_strengths") or {}
    swim = sports.get("swim", "?")
    bike = sports.get("bike", "?")
    run = sports.get("run", "?")
    fc = athlete.get("fc_max_bpm")
    ftp = athlete.get("ftp_watts")
    vma = athlete.get("vma_kmh")
    css = athlete.get("css_per_100m_s")

    lines = [
        "Athlète :",
        f"- FC max : {fc} bpm" if fc else "- FC max : non connue",
    ]
    if sport == "bike":
        lines.append(f"- FTP : {ftp} W" if ftp else "- FTP : non connue")
    if sport == "run":
        lines.append(f"- VMA : {vma} km/h" if vma else "- VMA : non connue")
    if sport == "swim":
        lines.append(f"- CSS : {css} s/100m" if css else "- CSS : non connue")
    lines.append(f"- Niveau (1-5) : swim={swim}, bike={bike}, run={run}")
    weak = [s for s in ("swim", "bike", "run") if isinstance(sports.get(s), int) and sports[s] <= 2]
    if weak:
        lines.append(
            "- Consigne intensité : pour les disciplines faibles "
            f"({', '.join(weak)}), privilégie l'endurance et la technique, "
            "limite l'intensité (pas d'intervalles seuil durs)."
        )
    return lines


def _activity_review_lines(activity_review: Any) -> list[str]:
    if not isinstance(activity_review, dict):
        return []

    lines = [
        "",
        "Revue activités récentes :",
        f"- 7 derniers jours : {activity_review.get('activities_7d', 0)} activités, "
        f"{activity_review.get('tss_7d', 0)} TSS, "
        f"{activity_review.get('elevation_gain_7d', 0)}m D+.",
    ]
    insights = activity_review.get("insights") or []
    lines.extend(
        f"- {insight['message']}"
        for insight in insights[:3]
        if isinstance(insight, dict) and insight.get("message")
    )
    return lines


def _build_user_prompt(
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_context: dict[str, Any],
) -> str:
    minutes = session["target_duration_s"] // 60
    target_dplus = session.get("target_elevation_gain_m")
    elevation_line = (
        f", dénivelé cible {target_dplus}m D+" if target_dplus and int(target_dplus) > 0 else ""
    )
    lines = [
        f"Session : {session['sport']} {session['session_type']} en phase {session['phase']}, "
        f"durée cible {minutes}min, TSS {session['target_tss']}{elevation_line}.",
        "",
    ]
    lines.extend(_athlete_lines(athlete=athlete, sport=str(session["sport"])))
    lines.extend(
        [
            "",
            f"Course objectif (dans {race_context['weeks_to_race']} semaines) :",
            f"- Discipline : {race_context['discipline']}",
            f"- Dénivelé total : {race_context['total_elevation_gain_m']}m",
        ]
    )
    lines.extend(_activity_review_lines(race_context.get("activity_review")))
    if session.get("coach_context"):
        lines.extend(["", f"Contexte coach : {session['coach_context']}"])
    lines.extend(["", describe_session_envelope(session)])
    return "\n".join(lines)


def _call_and_validate(
    client: Any, model: str, messages: list[dict[str, str]], session: dict[str, Any]
) -> tuple[Workout, LlmUsage]:
    """One LLM round-trip + validation. Raises OpenAIError on any failure."""
    try:
        resp = client.beta.chat.completions.parse(
            model=model, messages=messages, response_format=Workout
        )
    except Exception as e:
        raise OpenAIError(f"OpenAI call failed: {e}") from e
    usage = LlmUsage(
        model=model,
        prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
        completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
    )
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        raise OpenAIError("OpenAI returned no parsed payload")
    payload = parsed.model_dump()
    try:
        workout = Workout.model_validate(payload)
        return validate_workout_for_session(workout, session), usage
    except ValueError as e:
        raise OpenAIError(
            f"OpenAI returned unrealistic workout: {e}",
            raw_payload=json.dumps(payload, ensure_ascii=False),
        ) from e


def generate_workout_for_session(
    *,
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_context: dict[str, Any],
) -> WorkoutResult:
    """Call OpenAI with structured output, retrying with corrective feedback.

    A small model regularly returns a workout that breaks the numeric envelope
    (warmup cap, main-work ratio, total duration). Instead of failing the whole
    session on the first bad draw, re-prompt with the exact validation error so
    the model can self-correct, up to ``openai_max_attempts`` times.

    Only the final, successful attempt's token usage is returned — failed
    attempts also cost tokens but are not summed here (finops V1 is an
    estimate, not a to-the-cent reconciliation; see the openai_billing_snapshot
    ground-truth comparison for the real invoiced amount).
    """
    client = _get_client()
    settings = get_settings()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(session, athlete, race_context)},
    ]
    last_error: OpenAIError | None = None
    for _ in range(settings.openai_max_attempts):
        try:
            workout, usage = _call_and_validate(client, settings.openai_model, messages, session)
            return WorkoutResult(workout=workout, usage=usage)
        except OpenAIError as e:
            last_error = e
            if e.raw_payload:
                messages.append({"role": "assistant", "content": e.raw_payload})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"La séance précédente est invalide : {e}. "
                        "Corrige uniquement ce point en respectant les contraintes chiffrées "
                        "déjà fournies, et renvoie le workout complet."
                    ),
                }
            )
    raise last_error or OpenAIError("workout generation failed")
