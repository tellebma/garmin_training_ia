"""Tests de l'endpoint /coach/chat.

Le point sensible n'est pas le chemin nominal mais l'ordre des vérifications :
le rate limit insère une ligne à chaque appel, il ne doit donc pas être consommé
par un utilisateur dont le chat est de toute façon coupé.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fastapi import FastAPI


class ASGITestClient:
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def post(self, path: str, **kwargs: object) -> httpx.Response:
        return asyncio.run(self._request("POST", path, **kwargs))

    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)


@pytest.fixture
def client() -> ASGITestClient:
    from garmin_sync.main import app

    return ASGITestClient(app)


@pytest.fixture
def _authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")


_HEADERS = {"Authorization": "Bearer jwt"}
_BODY: dict[str, Any] = {"question": "Suis-je prêt pour samedi ?"}


def test_chat_requires_jwt(client: ASGITestClient) -> None:
    assert client.post("/coach/chat", json=_BODY).status_code == 401


@pytest.mark.usefixtures("_authenticated")
def test_chat_rejects_empty_question(client: ASGITestClient) -> None:
    r = client.post("/coach/chat", json={"question": ""}, headers=_HEADERS)
    assert r.status_code == 422


@pytest.mark.usefixtures("_authenticated")
def test_chat_rejects_oversized_question(client: ASGITestClient) -> None:
    """Une question de 50 000 caractères est un vecteur de coût, pas un usage."""
    r = client.post("/coach/chat", json={"question": "x" * 50_000}, headers=_HEADERS)
    assert r.status_code == 422


@pytest.mark.usefixtures("_authenticated")
def test_chat_returns_answer(client: ASGITestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from garmin_sync.coach import rate_limit
    from garmin_sync.coach.chat import agent, budget

    monkeypatch.setattr(budget, "check_or_raise", lambda **_: None)
    monkeypatch.setattr(budget, "remaining_usd", lambda **_: 1.42)
    monkeypatch.setattr(rate_limit, "check_or_raise", lambda **_: None)
    monkeypatch.setattr(
        agent,
        "run_chat",
        lambda **_: agent.ChatResult(
            conversation_id="c1", answer="Oui.", tools_used=["get_form_state"], rounds=2
        ),
    )

    r = client.post("/coach/chat", json=_BODY, headers=_HEADERS)

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["answer"] == "Oui."
    assert body["tools_used"] == ["get_form_state"]
    assert body["remaining_usd"] == 1.42


@pytest.mark.usefixtures("_authenticated")
def test_disabled_chat_does_not_consume_the_rate_limit(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync.coach import rate_limit
    from garmin_sync.coach.chat import budget

    calls: list[str] = []

    def _refuse(**_: object) -> None:
        raise budget.ChatDisabled("chat désactivé")

    monkeypatch.setattr(budget, "check_or_raise", _refuse)
    monkeypatch.setattr(rate_limit, "check_or_raise", lambda **_: calls.append("rate"))

    r = client.post("/coach/chat", json=_BODY, headers=_HEADERS)

    assert r.json()["status"] == "chat_disabled"
    assert calls == [], "le rate limit ne doit pas être consommé quand le chat est coupé"


@pytest.mark.usefixtures("_authenticated")
def test_budget_exceeded_is_reported_cleanly(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync.coach.chat import budget

    def _refuse(**_: object) -> None:
        raise budget.BudgetExceeded("quota mensuel atteint ($1.50 / $1.50)")

    monkeypatch.setattr(budget, "check_or_raise", _refuse)

    body = client.post("/coach/chat", json=_BODY, headers=_HEADERS).json()

    assert body["status"] == "budget_exceeded"
    assert body["remaining_usd"] == 0.0


@pytest.mark.usefixtures("_authenticated")
def test_rate_limited_returns_retry_hint(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync.coach import rate_limit
    from garmin_sync.coach.chat import budget

    monkeypatch.setattr(budget, "check_or_raise", lambda **_: None)

    def _limited(**_: object) -> None:
        raise rate_limit.RateLimited("too many")

    monkeypatch.setattr(rate_limit, "check_or_raise", _limited)

    body = client.post("/coach/chat", json=_BODY, headers=_HEADERS).json()

    assert body["status"] == "rate_limited"
    assert body["retry_after_seconds"] > 0


@pytest.mark.usefixtures("_authenticated")
def test_unknown_conversation_is_not_an_error(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une conversation d'un autre athlète est indistinguable d'une inexistante."""
    from garmin_sync.coach import rate_limit
    from garmin_sync.coach.chat import agent, budget, store

    monkeypatch.setattr(budget, "check_or_raise", lambda **_: None)
    monkeypatch.setattr(rate_limit, "check_or_raise", lambda **_: None)

    def _not_found(**_: object) -> None:
        raise store.ConversationNotFound("c9")

    monkeypatch.setattr(agent, "run_chat", _not_found)

    body = client.post(
        "/coach/chat", json={**_BODY, "conversation_id": "c9"}, headers=_HEADERS
    ).json()

    assert body["status"] == "conversation_not_found"
