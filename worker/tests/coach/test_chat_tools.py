"""Tests du catalogue d'outils du chat — le cloisonnement d'abord.

Le worker parle à Supabase en service role, donc RLS est court-circuité. Ces
tests vérifient la seule barrière qui reste entre un LLM et la base : le fait
que le ``user_id`` ne soit jamais choisi par le modèle.
"""

from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.chat import handlers
from garmin_sync.coach.chat.tools import (
    TOOLS,
    ToolError,
    execute_tool,
    openai_tool_specs,
)

_USER = "11111111-1111-1111-1111-111111111111"
_ATTACKER_TARGET = "22222222-2222-2222-2222-222222222222"


def _single_row(db, data):
    """Câble db.table().select().eq().maybe_single().execute().data."""
    chain = db.table.return_value.select.return_value.eq.return_value
    chain.maybe_single.return_value.execute.return_value.data = data


# --- Cloisonnement entre athlètes -------------------------------------------


def test_no_tool_exposes_user_id_in_its_schema():
    """Un outil qui accepterait user_id laisserait le modèle choisir sa cible."""
    for name, tool in TOOLS.items():
        properties = tool.parameters.get("properties", {})
        assert "user_id" not in properties, f"{name} expose user_id au modèle"
        assert "p_user_id" not in properties, f"{name} expose p_user_id au modèle"


def test_all_tool_schemas_forbid_extra_properties():
    """additionalProperties=False empêche le modèle d'injecter un champ inattendu."""
    for name, tool in TOOLS.items():
        assert tool.parameters.get("additionalProperties") is False, name


@patch("garmin_sync.coach.chat.tools.get_admin_client")
def test_execute_tool_ignores_user_id_forged_by_the_model(mock_db):
    """Le user_id passé dans les arguments est écarté au profit de celui du JWT."""
    db = MagicMock()
    mock_db.return_value = db
    _single_row(db, {})

    execute_tool("get_athlete_profile", {"user_id": _ATTACKER_TARGET}, user_id=_USER)

    # Le filtre appliqué est bien celui du JWT, pas celui suggéré par le modèle.
    eq_calls = db.table.return_value.select.return_value.eq.call_args_list
    assert eq_calls, "aucun filtre user_id appliqué"
    assert eq_calls[0].args == ("user_id", _USER)


@patch("garmin_sync.coach.chat.tools.get_admin_client")
def test_execute_tool_drops_unknown_arguments(mock_db):
    """Un argument hors schéma ne doit jamais atteindre le handler."""
    db = MagicMock()
    mock_db.return_value = db
    _single_row(db, {})

    # Si l'argument n'était pas filtré, le handler lèverait un TypeError.
    execute_tool("get_athlete_profile", {"table": "auth.users", "limit": 1}, user_id=_USER)


def test_execute_tool_rejects_unknown_tool():
    with pytest.raises(ToolError):
        execute_tool("drop_everything", {}, user_id=_USER)


# --- Plafonds serveur --------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(5000, handlers.MAX_ACTIVITIES), (0, 1), (-3, 1), (15, 15)],
)
def test_activity_limit_is_clamped_server_side(requested, expected):
    assert handlers._clamp(requested, 1, handlers.MAX_ACTIVITIES, 15) == expected


def test_clamp_falls_back_on_unreadable_values():
    """Le modèle produit parfois une chaîne là où un entier est attendu."""
    assert handlers._clamp("beaucoup", 1, 30, 15) == 15
    assert handlers._clamp(None, 1, 30, 15) == 15


@patch("garmin_sync.coach.chat.tools.get_admin_client")
def test_recent_activities_caps_limit_at_thirty(mock_db):
    db = MagicMock()
    mock_db.return_value = db
    # E24 : `.is_("excluded_at", "null")` avant l'ordre et la limite.
    chain = (
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.is_.return_value
    )
    chain.order.return_value.limit.return_value.execute.return_value.data = []

    execute_tool("get_recent_activities", {"limit": 9999}, user_id=_USER)

    chain.order.return_value.limit.assert_called_once_with(handlers.MAX_ACTIVITIES)


@patch("garmin_sync.coach.chat.tools.get_admin_client")
def test_activity_detail_requires_an_id(mock_db):
    mock_db.return_value = MagicMock()
    with pytest.raises(ToolError):
        execute_tool("get_activity_detail", {}, user_id=_USER)


# --- Minimisation des données ------------------------------------------------


@patch("garmin_sync.coach.chat.tools.get_admin_client")
def test_profile_never_selects_home_coordinates(mock_db):
    """lat/lon localisent le domicile : hors sujet pour un conseil d'entraînement."""
    db = MagicMock()
    mock_db.return_value = db
    _single_row(db, {})

    execute_tool("get_athlete_profile", {}, user_id=_USER)

    selected = db.table.return_value.select.call_args.args[0]
    for forbidden in ("lat", "lon", "consent", "cursor"):
        assert forbidden not in selected, f"{forbidden} ne doit pas sortir de la base"


@patch("garmin_sync.coach.chat.tools.get_admin_client")
def test_recent_activities_never_selects_the_gps_track(mock_db):
    db = MagicMock()
    mock_db.return_value = db
    chain = (
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.is_.return_value
    )
    chain.order.return_value.limit.return_value.execute.return_value.data = []

    execute_tool("get_recent_activities", {}, user_id=_USER)

    assert "route_polyline" not in db.table.return_value.select.call_args.args[0]


@patch("garmin_sync.coach.chat.tools.get_admin_client")
def test_profile_returns_age_not_date_of_birth(mock_db):
    db = MagicMock()
    mock_db.return_value = db
    _single_row(db, {"first_name": "Test", "dob": "1990-06-15"})

    result = execute_tool("get_athlete_profile", {}, user_id=_USER)

    assert "dob" not in result
    assert isinstance(result["age"], int)
    assert 20 <= result["age"] <= 80


# --- Schémas OpenAI ----------------------------------------------------------


def test_openai_specs_are_well_formed():
    specs = openai_tool_specs()
    assert len(specs) == len(TOOLS)
    for spec in specs:
        assert spec["type"] == "function"
        function = spec["function"]
        assert function["name"] in TOOLS
        # Une description vague fait qu'un outil n'est jamais appelé, et le
        # modèle répond alors de mémoire — c'est-à-dire qu'il invente.
        assert len(function["description"]) > 60
        assert function["parameters"]["type"] == "object"
