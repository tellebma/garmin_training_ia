from garmin_sync.coach.llm_pricing import compute_cost_usd


def test_compute_cost_usd_known_model():
    cost = compute_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 0.15 + 0.60


def test_compute_cost_usd_unknown_model_returns_zero():
    assert compute_cost_usd("some-future-model", prompt_tokens=1000, completion_tokens=1000) == 0.0


def test_compute_cost_usd_zero_tokens():
    assert compute_cost_usd("gpt-4o-mini", prompt_tokens=0, completion_tokens=0) == 0.0
