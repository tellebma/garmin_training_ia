"""Tests for profile_sync transformer + orchestrator."""

from __future__ import annotations

import pytest

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
