from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.openai_client import (
    OpenAIError,
    _athlete_lines,
    generate_workout_for_session,
)


def test_athlete_lines_warns_low_level_intensity():
    lines = _athlete_lines(
        athlete={"sports_strengths": {"swim": 1, "bike": 3, "run": 2}}, sport="run"
    )
    text = "\n".join(lines)
    assert "1-5" in text
    assert "intensité" in text.lower()


def test_athlete_lines_no_intensity_warning_when_all_strong():
    lines = _athlete_lines(
        athlete={"sports_strengths": {"swim": 3, "bike": 4, "run": 5}}, sport="bike"
    )
    text = "\n".join(lines)
    assert "Consigne intensité" not in text


def test_athlete_lines_includes_css_for_swim_when_known():
    lines = _athlete_lines(athlete={"css_per_100m_s": 95}, sport="swim")
    text = "\n".join(lines)
    assert "CSS" in text
    assert "95" in text


def test_athlete_lines_css_unknown_for_swim():
    lines = _athlete_lines(athlete={}, sport="swim")
    text = "\n".join(lines)
    assert "CSS : non connue" in text


def test_athlete_lines_no_css_line_for_bike():
    lines = _athlete_lines(athlete={"css_per_100m_s": 95}, sport="bike")
    text = "\n".join(lines)
    assert "CSS" not in text


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
        MagicMock(message=MagicMock(parsed=MagicMock(model_dump=lambda: _full_workout_dict())))
    ]

    result = generate_workout_for_session(
        session=_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    assert result.workout.summary_md.startswith("Séance")
    assert len(result.workout.main) == 1


def _full_workout_dict():
    return {
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
            "duration_s": 480,
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


@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_returns_usage_alongside_workout(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_resp = mock_client.beta.chat.completions.parse.return_value
    mock_resp.choices = [
        MagicMock(message=MagicMock(parsed=MagicMock(model_dump=lambda: _full_workout_dict())))
    ]
    mock_resp.usage = MagicMock(prompt_tokens=1200, completion_tokens=340)

    result = generate_workout_for_session(
        session=_session(), athlete=_athlete_full(), race_context=_race_context()
    )

    assert result.workout.total_duration_s() > 0
    assert result.usage.model == "gpt-4o-mini"
    assert result.usage.prompt_tokens == 1200
    assert result.usage.completion_tokens == 340


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
            "main": [{"duration_s": 2520, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
            "cooldown": {"duration_s": 480, "target": {"label": "Z1", "rpe": 2}, "notes": None},
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
    system_msg = call_args.kwargs["messages"][0]["content"]
    assert "55%" not in system_msg  # plus de ratio codé en dur : l'enveloppe par séance fait foi
    assert "Ne génère jamais de workout" in system_msg


@patch("garmin_sync.coach.openai_client._get_client")
def test_system_prompt_documents_sprint_and_pma_rules(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.beta.chat.completions.parse.return_value = _resp(_workout_dict(300, 3000, 300))
    generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    system_msg = mock_client.beta.chat.completions.parse.call_args.kwargs["messages"][0]["content"]
    assert '"pma"' in system_msg
    assert '"sprint"' in system_msg
    assert "VO2max" in system_msg or "plafond aérobie" in system_msg


@patch("garmin_sync.coach.openai_client._get_client")
def test_prompt_includes_activity_review_context(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    parsed = MagicMock(
        model_dump=lambda: {
            "warmup": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
            "main": [{"duration_s": 2520, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
            "cooldown": {"duration_s": 480, "target": {"label": "Z1", "rpe": 2}, "notes": None},
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


def _block(duration_s: int, label: str = "Z2", rpe: int = 4) -> dict:
    return {"duration_s": duration_s, "target": {"label": label, "rpe": rpe}, "notes": None}


def _workout_dict(warmup_s: int, main_s: int, cooldown_s: int) -> dict:
    return {
        "warmup": _block(warmup_s, "Z1", 2),
        "main": [_block(main_s)],
        "cooldown": _block(cooldown_s, "Z1", 2),
        "summary_md": "ok",
        "technical_focus": None,
    }


def _resp(workout_dict: dict) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(parsed=MagicMock(model_dump=lambda: workout_dict)))]
    return resp


def _endurance_session() -> dict:
    return {
        "sport": "bike",
        "session_type": "endurance",
        "target_duration_s": 3600,
        "target_tss": 60,
        "phase": "build",
    }


@patch("garmin_sync.coach.openai_client._get_client")
def test_prompt_includes_numeric_envelope(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.beta.chat.completions.parse.return_value = _resp(_workout_dict(300, 3000, 300))
    generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    user_msg = mock_client.beta.chat.completions.parse.call_args.kwargs["messages"][1]["content"]
    assert "75%" in user_msg  # endurance main-work floor surfaced to the model


@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_retries_with_feedback_then_succeeds(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    invalid = _workout_dict(1800, 1500, 300)  # warmup 1800s > endurance cap 900s
    valid = _workout_dict(300, 3000, 300)
    mock_client.beta.chat.completions.parse.side_effect = [_resp(invalid), _resp(valid)]

    result = generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )

    assert result.workout.warmup.duration_s == 300
    assert mock_client.beta.chat.completions.parse.call_count == 2
    # the corrective feedback (validation error) is fed back into the retry prompt
    retry_messages = mock_client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"]
    retry_text = "\n".join(m["content"] for m in retry_messages)
    assert "warmup" in retry_text  # the failing dimension is named
    assert "1800" in retry_text  # the offending value is fed back


@patch("garmin_sync.coach.openai_client._get_client")
def test_retry_feeds_previous_assistant_response(mock_get_client):
    """Le retry doit inclure la réponse assistant fautive : sans elle, le message
    'la séance précédente est invalide' réfère à un contenu que le modèle ne voit pas."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    invalid = _workout_dict(1800, 1500, 300)
    valid = _workout_dict(300, 3000, 300)
    mock_client.beta.chat.completions.parse.side_effect = [_resp(invalid), _resp(valid)]

    generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )

    retry_messages = mock_client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"]
    roles = [m["role"] for m in retry_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert "1800" in retry_messages[2]["content"]  # le workout fautif complet est visible


@patch("garmin_sync.coach.openai_client._get_client")
def test_api_failure_retry_has_no_assistant_message(mock_get_client):
    """Un échec réseau (pas de payload) ne doit pas injecter de message assistant vide."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    valid = _workout_dict(300, 3000, 300)
    mock_client.beta.chat.completions.parse.side_effect = [Exception("boom"), _resp(valid)]

    generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )

    retry_messages = mock_client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"]
    assert [m["role"] for m in retry_messages] == ["system", "user", "user"]


@patch("garmin_sync.coach.openai_client.get_settings")
@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_raises_after_max_attempts(mock_get_client, mock_get_settings):
    mock_get_settings.return_value = MagicMock(openai_model="gpt-4o-mini", openai_max_attempts=2)
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    invalid = _workout_dict(1800, 1500, 300)
    mock_client.beta.chat.completions.parse.return_value = _resp(invalid)

    with pytest.raises(OpenAIError, match="unrealistic workout"):
        generate_workout_for_session(
            session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
        )
    assert mock_client.beta.chat.completions.parse.call_count == 2


@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_rejects_unrealistic_structure(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    parsed = MagicMock(
        model_dump=lambda: {
            "warmup": {"duration_s": 900, "target": {"label": "Z1", "rpe": 2}, "notes": None},
            "main": [{"duration_s": 1080, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
            "cooldown": {"duration_s": 720, "target": {"label": "Z1", "rpe": 2}, "notes": None},
            "summary_md": "Trop peu de corps de séance.",
            "technical_focus": None,
        }
    )
    mock_client.beta.chat.completions.parse.return_value.choices = [
        MagicMock(message=MagicMock(parsed=parsed))
    ]

    with pytest.raises(OpenAIError, match="unrealistic workout"):
        generate_workout_for_session(
            session={
                **_session(),
                "sport": "bike",
                "session_type": "endurance",
                "target_duration_s": 2700,
            },
            athlete=_athlete_full(),
            race_context=_race_context(),
        )
