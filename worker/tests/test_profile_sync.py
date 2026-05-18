"""Tests for profile_sync transformer + orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from garminconnect import GarminConnectTooManyRequestsError

from garmin_sync.garmin_client import GarminAuthError
from garmin_sync.profile_sync import _normalize_sex, _transform_profile, _vma_from_vo2max


def test_transform_profile_full_payload() -> None:
    user_profile = {
        "birthDate": "1990-04-12",
        "gender": "MALE",
        "functionalThresholdPower": 245,
        "userMaxHr": 188,
    }
    max_metrics = {"vo2MaxValueRunning": 57.75}

    row = _transform_profile(user_profile, max_metrics)

    assert row == {"ftp_watts": 245, "vma_kmh": 16.5, "fc_max_bpm": 188}
    assert "dob" not in row  # NEVER touch dob — saisi à l'étape Perso
    assert "sex" not in row  # idem


def test_transform_profile_excludes_none_keys() -> None:
    """If Garmin has no value for a field, we must NOT include the key — the
    UPDATE would otherwise overwrite a manually-entered value with null."""
    user_profile = {"functionalThresholdPower": None, "userMaxHr": 188}
    max_metrics = {"vo2MaxValueRunning": None}

    row = _transform_profile(user_profile, max_metrics)

    assert row == {"fc_max_bpm": 188}
    assert "ftp_watts" not in row
    assert "vma_kmh" not in row


def test_transform_profile_empty_payload_returns_empty() -> None:
    row = _transform_profile({}, {})
    assert row == {}


def test_vma_from_vo2max() -> None:
    assert _vma_from_vo2max(56.0) == 16.0
    assert _vma_from_vo2max(57.75) == 16.5
    assert _vma_from_vo2max(None) is None
    assert _vma_from_vo2max(0) is None  # falsy → None, garde contre divisions weird


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MALE", "M"),
        ("FEMALE", "F"),
        ("male", "M"),
        ("OTHER", "X"),
        ("UNKNOWN", None),
        (None, None),
    ],
)
def test_normalize_sex(raw, expected) -> None:
    assert _normalize_sex(raw) == expected


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


def _make_creds_row(token_plain: str = '{"oauth": "ok"}') -> dict[str, object]:  # noqa: S107
    from garmin_sync.crypto import TokenCipher

    cipher = TokenCipher()
    return {"oauth_tokens_encrypted": cipher.encrypt(token_plain).decode("ascii")}


def test_sync_garmin_profile_returns_no_credentials_when_missing() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None  # noqa: E501

    with patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db):
        result = sync_garmin_profile("u1")

    assert result == {"status": "no_credentials"}


def test_sync_garmin_profile_returns_auth_failed_on_dead_token() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens") as login_mock,
    ):
        login_mock.side_effect = GarminAuthError("session expired")
        result = sync_garmin_profile("u1")

    assert result == {"status": "auth_failed"}


def test_sync_garmin_profile_returns_rate_limited_on_429() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )
    fake_client = MagicMock()
    fake_client.get_user_profile.side_effect = GarminConnectTooManyRequestsError("429")

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens", return_value=fake_client),
    ):
        result = sync_garmin_profile("u1")

    assert result == {"status": "rate_limited"}


def test_sync_garmin_profile_happy_path_upserts_only_present_fields() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )
    fake_client = MagicMock()
    fake_client.get_user_profile.return_value = {
        "functionalThresholdPower": 245,
        "userMaxHr": 188,
    }
    fake_client.get_max_metrics.return_value = {"vo2MaxValueRunning": 57.75}

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens", return_value=fake_client),
    ):
        result = sync_garmin_profile("u1")

    assert result["status"] == "ok"
    assert result["fetched"] == {"ftp_watts": 245, "vma_kmh": 16.5, "fc_max_bpm": 188}
    update_call = fake_db.table.return_value.update.call_args
    payload = update_call.args[0]
    assert payload["ftp_watts"] == 245
    assert payload["vma_kmh"] == 16.5
    assert payload["fc_max_bpm"] == 188
    assert "garmin_synced_at" in payload
    assert "dob" not in payload
    assert "sex" not in payload


def test_sync_garmin_profile_happy_path_only_garmin_synced_at_when_empty() -> None:
    """If Garmin returned nothing useful, the UPDATE still bumps garmin_synced_at
    so the UI knows we tried (and the wizard step Perf doesn't re-trigger)."""
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )
    fake_client = MagicMock()
    fake_client.get_user_profile.return_value = {}
    fake_client.get_max_metrics.return_value = {}

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens", return_value=fake_client),
    ):
        result = sync_garmin_profile("u1")

    assert result["status"] == "ok"
    assert result["fetched"] == {}
    payload = fake_db.table.return_value.update.call_args.args[0]
    assert list(payload.keys()) == ["garmin_synced_at"]
