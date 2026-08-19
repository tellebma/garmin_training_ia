"""Tests de la boucle de tool calling du chat."""

from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.chat import agent

_USER = "11111111-1111-1111-1111-111111111111"
_CONV = "33333333-3333-3333-3333-333333333333"


def _tool_call(name: str, arguments: str = "{}", call_id: str = "call_1") -> MagicMock:
    call = MagicMock()
    call.id = call_id
    call.function.name = name
    call.function.arguments = arguments
    return call


def _response(*, content: str | None = None, tool_calls: list | None = None) -> MagicMock:
    resp = MagicMock()
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 20
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    resp.choices = [MagicMock(message=message)]
    return resp


@pytest.fixture
def patched(monkeypatch):
    """Neutralise persistance, quotas et facturation : on teste la boucle."""
    monkeypatch.setattr(agent.store, "create_conversation", lambda **_: _CONV)
    monkeypatch.setattr(agent.store, "assert_owned", lambda **_: None)
    monkeypatch.setattr(agent.store, "load_history", lambda **_: [])
    monkeypatch.setattr(agent.store, "append_message", lambda **_: None)
    monkeypatch.setattr(agent.store, "touch_conversation", lambda **_: None)
    monkeypatch.setattr(agent, "resolve_chat_model", lambda: "gpt-5.6-luna")
    recorded: dict = {}
    monkeypatch.setattr(agent, "record_llm_usage", lambda **kw: recorded.update(kw))
    return recorded


def test_answers_directly_when_no_tool_is_needed(patched):
    client = MagicMock()
    client.chat.completions.create.return_value = _response(content="Repose-toi.")

    with patch.object(agent, "_get_client", return_value=client):
        result = agent.run_chat(user_id=_USER, question="Ça va ?")

    assert result.answer == "Repose-toi."
    assert result.rounds == 1
    assert result.tools_used == []


def test_runs_a_tool_then_answers(patched):
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(tool_calls=[_tool_call("get_form_state")]),
        _response(content="Ton TSB est à -13."),
    ]

    with (
        patch.object(agent, "_get_client", return_value=client),
        patch.object(agent, "execute_tool", return_value={"tsb": -13.4}) as exec_tool,
    ):
        result = agent.run_chat(user_id=_USER, question="Je suis frais ?")

    assert result.tools_used == ["get_form_state"]
    assert result.rounds == 2
    # Le user_id transmis à l'outil est celui du JWT, jamais un argument du modèle.
    assert exec_tool.call_args.kwargs["user_id"] == _USER


def test_stops_offering_tools_on_the_last_round(patched):
    """Un modèle qui boucle doit être forcé de conclure, pas servi indéfiniment."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        *[
            _response(tool_calls=[_tool_call("get_form_state")])
            for _ in range(agent.MAX_TOOL_ROUNDS)
        ],
        _response(content="Voici ce que je peux dire."),
    ]

    with (
        patch.object(agent, "_get_client", return_value=client),
        patch.object(agent, "execute_tool", return_value={"ok": True}),
    ):
        result = agent.run_chat(user_id=_USER, question="boucle")

    assert result.rounds == agent.MAX_TOOL_ROUNDS + 1
    last_kwargs = client.chat.completions.create.call_args_list[-1].kwargs
    assert "tools" not in last_kwargs, "le dernier tour doit retirer les outils"


def test_oversized_tool_result_is_truncated_and_flagged(patched):
    """Un résultat volumineux est réinjecté à chaque tour suivant : il faut le borner."""
    huge = {"rows": ["x" * 100 for _ in range(500)]}
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(tool_calls=[_tool_call("get_recent_activities")]),
        _response(content="ok"),
    ]

    with (
        patch.object(agent, "_get_client", return_value=client),
        patch.object(agent, "execute_tool", return_value=huge),
    ):
        agent.run_chat(user_id=_USER, question="tout mon historique")

    second_call_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_message = next(m for m in second_call_messages if m["role"] == "tool")
    assert "TRONQUÉ" in tool_message["content"]
    assert len(tool_message["content"]) < len(str(huge))


def test_tool_failure_is_reported_to_the_model_not_raised(patched):
    """Le modèle doit pouvoir se corriger plutôt que voir la requête échouer."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(tool_calls=[_tool_call("get_activity_detail")]),
        _response(content="Il me faut un id."),
    ]

    with (
        patch.object(agent, "_get_client", return_value=client),
        patch.object(agent, "execute_tool", side_effect=agent.ToolError("activity_id est requis")),
    ):
        result = agent.run_chat(user_id=_USER, question="analyse ma sortie")

    assert result.answer == "Il me faut un id."
    messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_message = next(m for m in messages if m["role"] == "tool")
    assert "activity_id est requis" in tool_message["content"]


def test_usage_is_billed_under_the_chat_feature(patched):
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(tool_calls=[_tool_call("get_form_state")]),
        _response(content="ok"),
    ]

    with (
        patch.object(agent, "_get_client", return_value=client),
        patch.object(agent, "execute_tool", return_value={}),
    ):
        agent.run_chat(user_id=_USER, question="q")

    assert patched["feature"] == "chat"
    # Les deux appels sont facturés, pas seulement celui qui a produit la réponse.
    assert patched["prompt_tokens"] == 200
    assert patched["completion_tokens"] == 40


def test_empty_question_is_rejected(patched):
    with pytest.raises(ValueError, match="question vide"):
        agent.run_chat(user_id=_USER, question="   ")


def test_malformed_tool_arguments_do_not_crash_the_loop(patched):
    """Le modèle produit parfois du JSON invalide dans arguments."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(tool_calls=[_tool_call("get_form_state", arguments="{not json")]),
        _response(content="ok"),
    ]

    with (
        patch.object(agent, "_get_client", return_value=client),
        patch.object(agent, "execute_tool", return_value={}) as exec_tool,
    ):
        agent.run_chat(user_id=_USER, question="q")

    assert exec_tool.call_args.args[1] == {}
