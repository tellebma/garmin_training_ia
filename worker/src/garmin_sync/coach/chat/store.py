"""Persistance des conversations du chat coach.

Le worker (service role) est seul écrivain : le client ne peut que lire ses
propres lignes. Si l'insertion de messages était ouverte côté client, un
utilisateur pourrait forger un message ``assistant`` et empoisonner le contexte
renvoyé au modèle au tour suivant.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

# Nombre de messages d'historique réinjectés dans le contexte. Au-delà, le coût
# par message croît linéairement avec la longueur de la conversation : à 50
# messages le contexte pèse ~100 k tokens, soit ~$0.08 pour un seul tour.
HISTORY_MESSAGES = 8

TITLE_MAX_CHARS = 80


class ConversationNotFound(Exception):
    """Conversation inexistante ou appartenant à un autre athlète."""


def create_conversation(*, user_id: str, first_message: str) -> str:
    """Crée une conversation titrée depuis le premier message (pas d'appel LLM
    pour générer un titre : ce serait un coût récurrent pour un gain cosmétique)."""
    title = first_message.strip().replace("\n", " ")[:TITLE_MAX_CHARS] or "Nouvelle conversation"
    resp = (
        get_admin_client()
        .table("coach_conversations")
        .insert({"user_id": user_id, "title": title})
        .execute()
    )
    rows = cast("list[dict[str, Any]]", resp.data or [])
    return str(rows[0]["id"])


def assert_owned(*, user_id: str, conversation_id: str) -> None:
    """Vérifie l'appartenance avant toute écriture.

    Le worker court-circuite RLS : c'est ici que se joue le cloisonnement entre
    athlètes pour les écritures.
    """
    resp = (
        get_admin_client()
        .table("coach_conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise ConversationNotFound(conversation_id)


def load_history(*, user_id: str, conversation_id: str) -> list[dict[str, Any]]:
    """Derniers messages utilisateur/assistant, du plus ancien au plus récent.

    Les tours d'outils (``role='tool'``) sont volontairement exclus : ils sont
    persistés pour l'audit, mais les réinjecter ferait grossir le contexte sans
    rien apporter — le modèle rappellera l'outil s'il en a besoin, sur des
    données fraîches.
    """
    resp = (
        get_admin_client()
        .table("coach_messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .in_("role", ["user", "assistant"])
        .order("id", desc=True)
        .limit(HISTORY_MESSAGES)
        .execute()
    )
    rows = cast("list[dict[str, Any]]", resp.data or [])
    rows.reverse()
    return [{"role": r["role"], "content": r.get("content") or ""} for r in rows]


def append_message(
    *,
    user_id: str,
    conversation_id: str,
    role: str,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_name: str | None = None,
    tool_result_chars: int | None = None,
) -> None:
    """Ajoute un message. Best-effort : une panne d'écriture d'historique ne doit
    pas faire échouer une réponse déjà payée et rendue à l'utilisateur."""
    try:
        get_admin_client().table("coach_messages").insert(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "tool_calls": tool_calls,
                "tool_name": tool_name,
                "tool_result_chars": tool_result_chars,
            }
        ).execute()
    except Exception:
        log.exception("chat store: écriture du message impossible (conv=%s)", conversation_id)


def touch_conversation(*, conversation_id: str) -> None:
    try:
        # PostgREST n'évalue pas "now()" côté SQL : il l'écrirait comme une
        # chaîne littérale. Le timestamp est donc calculé ici.
        get_admin_client().table("coach_conversations").update(
            {"last_message_at": datetime.now(UTC).isoformat()}
        ).eq("id", conversation_id).execute()
    except Exception:
        log.exception("chat store: mise à jour de last_message_at impossible")
