from garmin_sync.coach.llm_pricing import MODEL_PRICING, compute_cost_usd
from garmin_sync.config import Settings


def test_compute_cost_usd_known_model():
    cost = compute_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 0.15 + 0.60


def test_compute_cost_usd_gpt_5_4_mini():
    cost = compute_cost_usd("gpt-5.4-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 0.75 + 4.50


def test_compute_cost_usd_gpt_5_6_luna():
    cost = compute_cost_usd("gpt-5.6-luna", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 0.20 + 1.20


def test_default_model_is_priced():
    """Un défaut absent de la table ferait retomber compute_cost_usd sur 0.0 et
    afficherait des coûts nuls dans la console admin."""
    assert Settings.model_fields["openai_model"].default in MODEL_PRICING


def test_compute_cost_usd_unknown_model_returns_zero():
    assert compute_cost_usd("some-future-model", prompt_tokens=1000, completion_tokens=1000) == 0.0


def test_compute_cost_usd_zero_tokens():
    assert compute_cost_usd("gpt-4o-mini", prompt_tokens=0, completion_tokens=0) == 0.0
