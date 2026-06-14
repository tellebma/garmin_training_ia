from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.openai_client import (
    OpenAIError,
    generate_workout_for_session,
)


def _athlete_full():
    return {
        "ftp_watts": 240,
        "vma_kmh": 17.0,
        "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }


def _race_context():
    return {"discipline": "triathlon", "total_elevation_gain_m": 350, "weeks_to_race": 12}


def _race_context_with_activity_review():
    ctx = _race_context()
    ctx["activity_review"] = {
        "activities_7d": 3,
        "tss_7d": 240,
        "elevation_gain_7d": 900,
        "insights": [
            {
                "name": "load_spike",
                "severity": "risk",
                "message": "Charge récente nettement au-dessus de la tendance.",
            }
        ],
    }
    return ctx


def _session():
    return {
        "sport": "run",
        "session_type": "threshold",
        "target_duration_s": 3600,
        "target_tss": 75,
        "phase": "build",
    }


@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_returns_validated_workout(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.beta.chat.completions.parse.return_value.choices = [
        MagicMock(
            message=MagicMock(
                parsed=MagicMock(
                    model_dump=lambda: {
                        "warmup": {
                            "duration_s": 600,
                            "target": {
                                "label": "Z1",
                                "rpe": 2,
                                "bpm_low": 130,
                                "bpm_high": 145,
                                "watts_low": None,
                                "watts_high": None,
                                "pace_low_kmh": None,
                                "pace_high_kmh": None,
                            },
                            "notes": None,
                        },
                        "main": [
                            {
                                "reps": 4,
                                "work": {
                                    "duration_s": 480,
                                    "target": {
                                        "label": "Z4",
                                        "rpe": 8,
                                        "bpm_low": 170,
                                        "bpm_high": 180,
                                        "watts_low": None,
                                        "watts_high": None,
                                        "pace_low_kmh": 14.0,
                                        "pace_high_kmh": 15.0,
                                    },
                                    "notes": None,
                                },
                                "rest": {
                                    "duration_s": 120,
                                    "target": {
                                        "label": "Z1",
                                        "rpe": 2,
                                        "bpm_low": 130,
                                        "bpm_high": 145,
                                        "watts_low": None,
                                        "watts_high": None,
                                        "pace_low_kmh": None,
                                        "pace_high_kmh": None,
                                    },
                                    "notes": None,
                                },
                            }
                        ],
                        "cooldown": {
                            "duration_s": 600,
                            "target": {
                                "label": "Z1",
                                "rpe": 2,
                                "bpm_low": 130,
                                "bpm_high": 145,
                                "watts_low": None,
                                "watts_high": None,
                                "pace_low_kmh": None,
                                "pace_high_kmh": None,
                            },
                            "notes": None,
                        },
                        "summary_md": "Séance seuil exigeante.",
                        "technical_focus": "Foulée tonique sur les répétitions.",
                    }
                )
            )
        )
    ]

    workout = generate_workout_for_session(
        session=_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    assert workout.summary_md.startswith("Séance")
    assert len(workout.main) == 1


@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_raises_on_openai_error(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.beta.chat.completions.parse.side_effect = Exception("boom")
    with pytest.raises(OpenAIError):
        generate_workout_for_session(
            session=_session(), athlete=_athlete_full(), race_context=_race_context()
        )


@patch("garmin_sync.coach.openai_client._get_client")
def test_prompt_includes_race_context(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    parsed = MagicMock(
        model_dump=lambda: {
            "warmup": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
            "main": [{"duration_s": 1800, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
            "cooldown": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
            "summary_md": "ok",
            "technical_focus": None,
        }
    )
    mock_client.beta.chat.completions.parse.return_value.choices = [
        MagicMock(message=MagicMock(parsed=parsed))
    ]
    generate_workout_for_session(
        session=_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    call_args = mock_client.beta.chat.completions.parse.call_args
    user_msg = call_args.kwargs["messages"][1]["content"]
    assert "triathlon" in user_msg
    assert "12 semaines" in user_msg
    assert "350m" in user_msg


@patch("garmin_sync.coach.openai_client._get_client")
def test_prompt_includes_activity_review_context(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    parsed = MagicMock(
        model_dump=lambda: {
            "warmup": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
            "main": [{"duration_s": 1800, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
            "cooldown": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
            "summary_md": "ok",
            "technical_focus": None,
        }
    )
    mock_client.beta.chat.completions.parse.return_value.choices = [
        MagicMock(message=MagicMock(parsed=parsed))
    ]
    session = {**_session(), "coach_context": "Garde une marge sur l'intensité."}
    generate_workout_for_session(
        session=session, athlete=_athlete_full(), race_context=_race_context_with_activity_review()
    )
    call_args = mock_client.beta.chat.completions.parse.call_args
    user_msg = call_args.kwargs["messages"][1]["content"]
    assert "Revue activités récentes" in user_msg
    assert "240 TSS" in user_msg
    assert "Charge récente" in user_msg
    assert "Garde une marge" in user_msg
