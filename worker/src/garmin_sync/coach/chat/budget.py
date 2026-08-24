"""Garde-fous de coût du chat coach (E11).

Un compteur d'appels ne protège de rien sur un chat : vingt messages courts
coûtent ~$0.03, vingt messages en fin de longue conversation coûtent ~$1.60, et
le compteur voit la même chose. Les quotas sont donc exprimés **en dollars**,
lus depuis ``llm_usage`` qui trace déjà chaque appel avec son coût.

Trois verrous indépendants :

1. ``chat_enabled`` — kill switch manuel (table ``feature_flags``) ;
2. quota mensuel par utilisateur ;
3. plafond mensuel global, qui **bascule le kill switch** quand il est franchi.

Le quatrième garde-fou vit ici aussi : l'allowlist de modèles. Passer de
``gpt-5.6-luna`` ($0.20/$1.20 par million) à ``gpt-5.6-sol`` ($5/$30) multiplie
la facture par 25 — une variable d'environnement mal renseignée suffirait, sans
qu'aucun compteur ne bouge.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

from garmin_sync.config import get_settings
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

USER_MONTHLY_BUDGET_USD = 1.50
GLOBAL_MONTHLY_BUDGET_USD = 20.00

CHAT_FEATURE_FLAG = "chat_enabled"

# Modèles dont le rapport qualité/prix a été validé pour le chat. Tout autre
# modèle est refusé au démarrage plutôt que découvert sur la facture.
ALLOWED_CHAT_MODELS = frozenset({"gpt-5.6-luna", "gpt-5.4-nano", "gpt-5-mini", "gpt-4o-mini"})


class ChatDisabled(Exception):
    """Le chat est coupé (kill switch ou budget global dépassé)."""


class BudgetExceeded(Exception):
    """L'utilisateur a épuisé son quota mensuel."""


class ModelNotAllowed(Exception):
    """Le modèle configuré n'est pas dans l'allowlist du chat."""


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _spend_usd(user_id: str | None) -> float:
    """Dépense LLM du mois courant, pour un utilisateur ou globale.

    Best-effort : si la RPC échoue, on renvoie 0 plutôt que de bloquer le chat.
    Un incident de lecture du compteur ne doit pas couper le service — le
    plafond global reste, lui, contrôlé par le kill switch.
    """
    try:
        resp = (
            get_admin_client()
            .rpc(
                "coach_llm_spend_usd",
                {"p_since": _month_start().isoformat(), "p_user_id": user_id},
            )
            .execute()
        )
        return float(cast("float | None", resp.data) or 0)
    except Exception:
        log.exception("chat budget: lecture de la dépense impossible (user=%s)", user_id)
        return 0.0


def _is_chat_enabled() -> bool:
    try:
        resp = (
            get_admin_client()
            .table("feature_flags")
            .select("enabled")
            .eq("key", CHAT_FEATURE_FLAG)
            .maybe_single()
            .execute()
        )
        row = cast("dict[str, Any] | None", resp.data if resp else None)
        return bool(row and row.get("enabled"))
    except Exception:
        log.exception("chat budget: lecture du feature flag impossible")
        return False


def _disable_chat(reason: str) -> None:
    """Bascule le kill switch. Le chat reste coupé jusqu'à réactivation manuelle."""
    try:
        get_admin_client().table("feature_flags").update(
            {"enabled": False, "description": f"Coupé automatiquement : {reason}"}
        ).eq("key", CHAT_FEATURE_FLAG).execute()
        log.error("chat budget: kill switch activé — %s", reason)
    except Exception:
        log.exception("chat budget: bascule du kill switch impossible")


def resolve_chat_model() -> str:
    """Modèle du chat, refusé s'il sort de l'allowlist."""
    model = get_settings().openai_model
    if model not in ALLOWED_CHAT_MODELS:
        msg = (
            f"Modèle '{model}' hors allowlist du chat ({sorted(ALLOWED_CHAT_MODELS)}). "
            "Un modèle non validé peut multiplier le coût par 25."
        )
        raise ModelNotAllowed(msg)
    return model


def check_or_raise(*, user_id: str) -> None:
    """Vérifie les trois verrous avant d'engager le moindre appel payant."""
    if not _is_chat_enabled():
        raise ChatDisabled("chat désactivé")

    global_spend = _spend_usd(None)
    if global_spend >= GLOBAL_MONTHLY_BUDGET_USD:
        _disable_chat(f"budget global mensuel atteint (${global_spend:.2f})")
        raise ChatDisabled(f"budget global mensuel atteint (${global_spend:.2f})")

    user_spend = _spend_usd(user_id)
    if user_spend >= USER_MONTHLY_BUDGET_USD:
        msg = f"quota mensuel atteint (${user_spend:.2f} / ${USER_MONTHLY_BUDGET_USD:.2f})"
        raise BudgetExceeded(msg)


def remaining_usd(*, user_id: str) -> float:
    """Reste à dépenser ce mois-ci, pour affichage côté UI."""
    return max(0.0, USER_MONTHLY_BUDGET_USD - _spend_usd(user_id))
