"""Tests des garde-fous de coût du chat."""

from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.chat import budget

_USER = "11111111-1111-1111-1111-111111111111"


def _db_with(flag_enabled: bool, spends: list[float]) -> MagicMock:
    """Base simulée : un feature flag et une suite de réponses de dépense."""
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value
    chain.maybe_single.return_value.execute.return_value.data = {"enabled": flag_enabled}
    db.rpc.return_value.execute.side_effect = [MagicMock(data=s) for s in spends]
    return db


@patch("garmin_sync.coach.chat.budget.get_admin_client")
def test_passes_when_flag_on_and_budgets_untouched(mock_db):
    mock_db.return_value = _db_with(True, [1.0, 0.10])  # global, puis user
    budget.check_or_raise(user_id=_USER)


@patch("garmin_sync.coach.chat.budget.get_admin_client")
def test_kill_switch_blocks_before_any_paid_call(mock_db):
    mock_db.return_value = _db_with(False, [])
    with pytest.raises(budget.ChatDisabled):
        budget.check_or_raise(user_id=_USER)


@patch("garmin_sync.coach.chat.budget.get_admin_client")
def test_user_quota_exceeded_raises(mock_db):
    mock_db.return_value = _db_with(True, [1.0, budget.USER_MONTHLY_BUDGET_USD])
    with pytest.raises(budget.BudgetExceeded):
        budget.check_or_raise(user_id=_USER)


@patch("garmin_sync.coach.chat.budget.get_admin_client")
def test_global_budget_exceeded_flips_the_kill_switch(mock_db):
    """Le plafond global ne se contente pas de refuser : il coupe le chat."""
    db = _db_with(True, [budget.GLOBAL_MONTHLY_BUDGET_USD + 1])
    mock_db.return_value = db

    with pytest.raises(budget.ChatDisabled):
        budget.check_or_raise(user_id=_USER)

    update_payload = db.table.return_value.update.call_args.args[0]
    assert update_payload["enabled"] is False


@patch("garmin_sync.coach.chat.budget.get_admin_client")
def test_spend_read_failure_does_not_block_the_chat(mock_db):
    """Un incident de lecture du compteur ne doit pas couper le service."""
    db = MagicMock()
    db.rpc.side_effect = RuntimeError("postgrest down")
    mock_db.return_value = db
    assert budget._spend_usd(_USER) == 0.0


@patch("garmin_sync.coach.chat.budget.get_admin_client")
def test_flag_read_failure_closes_the_chat(mock_db):
    """À l'inverse, un flag illisible ferme : on ne dépense pas dans le doute."""
    db = MagicMock()
    db.table.side_effect = RuntimeError("postgrest down")
    mock_db.return_value = db
    assert budget._is_chat_enabled() is False


def test_default_model_is_allowed():
    assert budget.resolve_chat_model() in budget.ALLOWED_CHAT_MODELS


@patch("garmin_sync.coach.chat.budget.get_settings")
def test_expensive_model_is_refused(mock_settings):
    """gpt-5.6-sol coûte 25x le modèle par défaut : refus au démarrage plutôt
    que découverte sur la facture."""
    mock_settings.return_value = MagicMock(openai_model="gpt-5.6-sol")
    with pytest.raises(budget.ModelNotAllowed):
        budget.resolve_chat_model()


def test_budgets_are_ordered_sanely():
    assert budget.USER_MONTHLY_BUDGET_USD < budget.GLOBAL_MONTHLY_BUDGET_USD
