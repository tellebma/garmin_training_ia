from itertools import pairwise

from garmin_sync.coach.training_days import (
    assign_sports,
    athlete_level,
    cap_niveau,
    cap_volume,
    repos_min,
    run_cap,
    select_training_days,
    training_days_count,
)


def test_cap_volume_by_hours():
    assert cap_volume(4) == 4
    assert cap_volume(6) == 5
    assert cap_volume(8) == 6
    assert cap_volume(10) == 6


def test_athlete_level_from_strengths():
    assert athlete_level({"swim": 1, "bike": 2, "run": 2}) == "beginner"
    assert athlete_level({"swim": 3, "bike": 3, "run": 3}) == "intermediate"
    assert athlete_level({"swim": 4, "bike": 5, "run": 4}) == "advanced"


def test_athlete_level_not_dragged_down_by_one_weak_discipline():
    """Régression #129 : un niveau 4 en vélo ne doit pas être classé beginner
    parce que la moyenne des trois disciplines passe sous 2,5 (run à 1)."""
    assert athlete_level({"swim": 2, "bike": 4, "run": 1}) != "beginner"


def test_level_label_for_score():
    from garmin_sync.coach.training_days import level_label_for_score

    assert level_label_for_score(1) == "beginner"
    assert level_label_for_score(2) == "beginner"
    assert level_label_for_score(3) == "intermediate"
    assert level_label_for_score(4) == "advanced"
    assert level_label_for_score(5) == "advanced"


def test_cap_niveau():
    assert cap_niveau("beginner") == 4
    assert cap_niveau("intermediate") == 5
    assert cap_niveau("advanced") == 6


def test_repos_min_beginner_floor_two():
    assert repos_min("beginner", "base") == 2
    assert repos_min("intermediate", "base") == 1
    assert repos_min("intermediate", "taper") == 2


def test_training_days_count_intermediate_7avail_8h():
    assert training_days_count(n_available=7, hours=8, level="intermediate", phase="build") == 5


def test_training_days_count_beginner_7avail_4h():
    assert training_days_count(n_available=7, hours=4, level="beginner", phase="base") == 4


def test_training_days_count_never_below_one_rest():
    assert training_days_count(n_available=7, hours=12, level="advanced", phase="build") <= 6


def test_select_spreads_days():
    chosen = select_training_days(available_idx={0, 1, 2, 3, 4, 5, 6}, count=5)
    assert len(chosen) == 5
    assert chosen <= {0, 1, 2, 3, 4, 5, 6}


def test_select_count_zero_returns_empty():
    assert select_training_days(available_idx={0, 2, 4}, count=0) == set()


def test_select_count_ge_available_returns_all():
    assert select_training_days(available_idx={0, 2, 4}, count=9) == {0, 2, 4}


def test_select_observed_days_follows_athlete_habits():
    """Régression #127 : l'athlète pose ses séances mar/jeu/sam/dim depuis des
    semaines, la grille mécanique lun/mer/ven/sam ne doit plus être reproposée."""
    from garmin_sync.coach.training_days import select_training_days_observed

    counts = {1: 4, 3: 3, 5: 5, 6: 4}  # mar, jeu, sam, dim
    chosen = select_training_days_observed(
        available_idx={0, 1, 2, 3, 4, 5, 6}, count=4, weekday_counts=counts
    )
    assert chosen == {1, 3, 5, 6}


def test_select_observed_days_falls_back_to_spread_when_sparse():
    from garmin_sync.coach.training_days import select_training_days_observed

    sparse = {2: 1}  # signal insuffisant
    chosen = select_training_days_observed(
        available_idx={0, 1, 2, 3, 4, 5, 6}, count=4, weekday_counts=sparse
    )
    assert chosen == select_training_days(available_idx={0, 1, 2, 3, 4, 5, 6}, count=4)


def test_select_observed_days_respects_availability_mask():
    from garmin_sync.coach.training_days import select_training_days_observed

    counts = {0: 9, 6: 8, 2: 5, 4: 4}
    chosen = select_training_days_observed(available_idx={2, 4, 5}, count=2, weekday_counts=counts)
    assert chosen <= {2, 4, 5}
    assert len(chosen) == 2


def test_long_session_day_prefers_athlete_biggest_day():
    """#127 : la séance longue suit le jour où l'athlète roule déjà longtemps."""
    from garmin_sync.coach.training_days import long_session_day

    # L'athlète fait ses grosses sorties le jeudi (durée cumulée max).
    durations = {1: 3600.0, 3: 15000.0, 5: 4000.0}
    assert long_session_day({1, 3, 5}, weekday_durations=durations) == 3
    # Sans signal : dernier jour d'entraînement (comportement #122).
    assert long_session_day({1, 3, 5}) == 5


def test_run_cap_by_level():
    assert run_cap("beginner") == 2
    assert run_cap("intermediate") == 3
    assert run_cap("advanced") == 4


def test_assign_sports_no_back_to_back_run():
    days = [0, 1, 2, 3, 4]
    assignment = assign_sports(training_idx=days, sport_counts={"swim": 1, "bike": 2, "run": 2})
    ordered = [assignment[d] for d in days]
    for a, b in pairwise(ordered):
        assert not (a == "run" and b == "run")


def test_assign_sports_puts_dominant_sport_on_long_day():
    assignment = assign_sports(
        training_idx=[0, 2, 4, 5], sport_counts={"swim": 1, "bike": 2, "run": 1}, long_day_idx=5
    )
    assert assignment[5] == "bike"


def test_assign_sports_empty_counts_falls_back_to_run():
    assert assign_sports(training_idx=[0, 2], sport_counts={}) == {0: "run", 2: "run"}


def test_allocate_sessions_bike_heavy_race_gets_more_bike_than_swim():
    """Régression #130 : une course dont le vélo pèse ~60 % du temps doit produire
    au moins autant de vélo que de natation (prod : 2 swim / 1 bike)."""
    from garmin_sync.coach.training_days import allocate_sport_sessions

    counts = allocate_sport_sessions(
        count=4,
        time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        strengths={"swim": 2, "bike": 4, "run": 1},
        run_cap_value=run_cap("intermediate"),
    )
    assert sum(counts.values()) == 4
    assert counts["bike"] >= 2
    assert counts["bike"] >= counts["swim"]
    # Chaque discipline de la course garde au moins une séance.
    assert all(c >= 1 for c in counts.values())


def test_allocate_sessions_respects_run_cap():
    from garmin_sync.coach.training_days import allocate_sport_sessions

    counts = allocate_sport_sessions(
        count=6,
        time_shares={"run": 0.8, "bike": 0.2},
        strengths={"run": 1, "bike": 3},
        run_cap_value=2,
    )
    assert counts["run"] <= 2
    assert sum(counts.values()) == 6


def test_allocate_sessions_fewer_days_than_sports_keeps_biggest_stakes():
    from garmin_sync.coach.training_days import allocate_sport_sessions

    counts = allocate_sport_sessions(
        count=2,
        time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        strengths={"swim": 3, "bike": 3, "run": 3},
        run_cap_value=None,
    )
    assert sum(counts.values()) == 2
    assert "bike" in counts  # l'enjeu dominant n'est jamais sacrifié


def test_allocate_sessions_reserves_one_brick_for_chained_race():
    """#154 : un triathlon doit recevoir une séance d'enchaînement par semaine."""
    from garmin_sync.coach.training_days import allocate_sport_sessions

    counts = allocate_sport_sessions(
        count=5,
        time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        strengths={"swim": 2, "bike": 4, "run": 1},
        run_cap_value=run_cap("intermediate"),
        with_brick=True,
    )
    assert counts["brick"] == 1
    assert sum(counts.values()) == 5
    # Le brick se substitue au volume : chaque discipline garde sa séance.
    for sport in ("swim", "bike", "run"):
        assert counts[sport] >= 1


def test_allocate_sessions_no_brick_by_default():
    from garmin_sync.coach.training_days import allocate_sport_sessions

    counts = allocate_sport_sessions(
        count=5,
        time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        strengths={"swim": 3, "bike": 3, "run": 3},
    )
    assert "brick" not in counts


def test_allocate_sessions_skips_brick_when_days_only_cover_the_disciplines():
    """3 jours pour 3 disciplines : pas de place pour un enchaînement en plus."""
    from garmin_sync.coach.training_days import allocate_sport_sessions

    counts = allocate_sport_sessions(
        count=3,
        time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        strengths={"swim": 3, "bike": 3, "run": 3},
        with_brick=True,
    )
    assert "brick" not in counts
    assert sum(counts.values()) == 3


def test_allocate_sessions_brick_counts_toward_the_run_impact_cap():
    """Le brick charge les jambes comme un run : il entre dans le plafond d'impact."""
    from garmin_sync.coach.training_days import allocate_sport_sessions

    counts = allocate_sport_sessions(
        count=6,
        time_shares={"swim": 0.10, "bike": 0.30, "run": 0.60},
        strengths={"swim": 3, "bike": 3, "run": 1},
        run_cap_value=2,
        with_brick=True,
    )
    assert counts["run"] + counts["brick"] <= 2
    assert sum(counts.values()) == 6


def test_assign_sports_falls_back_to_non_impact_rather_than_chaining_impact():
    """Reste du run/brick après un jour d'impact : on reporte sur le non-impact."""
    days = [0, 1, 2, 3]
    assignment = assign_sports(training_idx=days, sport_counts={"bike": 1, "run": 2, "brick": 1})
    ordered = [assignment[d] for d in days]
    for a, b in pairwise(ordered):
        assert not ({a, b} <= {"run", "brick"})


def test_assign_sports_never_chains_brick_and_run():
    days = [0, 1, 2, 3, 4]
    assignment = assign_sports(
        training_idx=days, sport_counts={"swim": 1, "bike": 2, "run": 1, "brick": 1}
    )
    ordered = [assignment[d] for d in days]
    for a, b in pairwise(ordered):
        assert not ({a, b} <= {"run", "brick"})
