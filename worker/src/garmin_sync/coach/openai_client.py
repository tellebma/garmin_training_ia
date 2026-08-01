"""Thin OpenAI client wrapper using structured outputs (Pydantic-typed responses)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import OpenAI

from garmin_sync.coach.workout_schema import (
    Workout,
    describe_session_envelope,
    enrich_workout_targets,
    validate_workout_for_session,
)
from garmin_sync.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlmUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class WorkoutResult:
    workout: Workout
    usage: LlmUsage
    attempts: int = 1


class OpenAIError(Exception):
    """Raised when the OpenAI API call or response is unusable.

    ``raw_payload`` porte le JSON du workout rejeté par la validation, pour
    ré-injection en message assistant lors du retry correctif.

    ``usage`` / ``attempts`` portent le coût cumulé des tentatives (y compris
    ratées) pour que l'appelant l'enregistre en finops même sur échec total —
    sinon 3 requêtes facturées disparaissent du comptage (cf. écart 622 req /
    11 lignes llm_usage observé en prod).
    """

    def __init__(
        self,
        message: str,
        raw_payload: str | None = None,
        usage: LlmUsage | None = None,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload
        self.usage = usage
        self.attempts = attempts


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

# Un coach écrit « 8×100 m départ 1'50 », jamais « 2160 secondes » (issue #125).
_SWIM_PROMPT_GUIDANCE = """Consignes natation (impératives) :
- Renseigne distance_m (en mètres, multiples de 25) pour chaque bloc : échauffement,
  éducatifs, séries, retour au calme.
- Structure type d'une séance : échauffement progressif, éducatifs (drills technique)
  en début de corps de séance, séries principales en sets répétés (reps + work + rest),
  retour au calme facile.
- Précise le départ des séries dans notes (ex : « départ toutes les 1'50 »).
- N'exprime jamais l'allure en km/h : pense en secondes par 100 m."""


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
    if session["sport"] == "swim":
        lines.extend(["", _SWIM_PROMPT_GUIDANCE])
    lines.extend(["", describe_session_envelope(session)])
    return "\n".join(lines)


def _attempt_workout(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    session: dict[str, Any],
) -> tuple[Workout | OpenAIError, int, int]:
    """Run one OpenAI call + envelope validation.

    Returns ``(workout_or_error, prompt_tokens, completion_tokens)`` — token
    counts are zero when the call itself failed (nothing billed).
    """
    try:
        resp = client.beta.chat.completions.parse(
            model=model, messages=messages, response_format=Workout
        )
    except Exception as e:  # API/network failure — no tokens billed
        return OpenAIError(f"OpenAI call failed: {e}"), 0, 0

    prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
    completion_tokens = resp.usage.completion_tokens if resp.usage else 0
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        return OpenAIError("OpenAI returned no parsed payload"), prompt_tokens, completion_tokens

    payload = parsed.model_dump()
    try:
        workout = validate_workout_for_session(Workout.model_validate(payload), session)
    except ValueError as e:
        # Log structuré du motif de rejet : permet de cibler les enveloppes
        # insatisfiables (ex : longues sorties vélo, cf. issue #124).
        log.warning(
            "workout validation rejected sport=%s type=%s target_s=%s reason=%s",
            session.get("sport"),
            session.get("session_type"),
            session.get("target_duration_s"),
            e,
        )
        error = OpenAIError(
            f"OpenAI returned unrealistic workout: {e}",
            raw_payload=json.dumps(payload, ensure_ascii=False),
        )
        return error, prompt_tokens, completion_tokens
    return workout, prompt_tokens, completion_tokens


def _append_corrective_feedback(messages: list[dict[str, str]], error: OpenAIError) -> None:
    # Feed the failure back for the corrective retry (assistant echo only when
    # a payload exists; a network failure has none).
    if error.raw_payload:
        messages.append({"role": "assistant", "content": error.raw_payload})
    messages.append(
        {
            "role": "user",
            "content": (
                f"La séance précédente est invalide : {error}. "
                "Corrige uniquement ce point en respectant les contraintes chiffrées "
                "déjà fournies, et renvoie le workout complet."
            ),
        }
    )


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

    Token usage is ACCUMULATED across every attempt (each retry is a separately
    billed request) and returned on the ``WorkoutResult`` — or attached to the
    raised ``OpenAIError`` on total failure — so finops counts the true cost, not
    just the last successful call.
    """
    client: Any = _get_client()
    settings = get_settings()
    model = settings.openai_model
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(session, athlete, race_context)},
    ]
    total_prompt = 0
    total_completion = 0
    attempts = 0
    last_error: OpenAIError | None = None

    for _ in range(settings.openai_max_attempts):
        attempts += 1
        result, prompt_tokens, completion_tokens = _attempt_workout(
            client, model, messages, session
        )
        total_prompt += prompt_tokens
        total_completion += completion_tokens
        if isinstance(result, Workout):
            # Bornes chiffrées (FC/W/allure) dérivées du profil : le LLM laisse
            # régulièrement ces champs à null (issue #125).
            enriched = enrich_workout_targets(
                result, athlete=athlete, sport=str(session.get("sport") or "")
            )
            return WorkoutResult(
                workout=enriched,
                usage=LlmUsage(model, total_prompt, total_completion),
                attempts=attempts,
            )
        last_error = result
        _append_corrective_feedback(messages, result)

    err = last_error or OpenAIError("workout generation failed")
    err.usage = LlmUsage(model, total_prompt, total_completion)
    err.attempts = attempts
    raise err
