"""Versioned USD/1M-token pricing per OpenAI model — updated by hand on price changes."""

from __future__ import annotations

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
}


def compute_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Returns 0.0 for an unknown model rather than raising — cost tracking must
    never block generation on a pricing table that hasn't caught up yet."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return 0.0
    return (prompt_tokens / 1_000_000) * pricing["input_per_1m"] + (
        completion_tokens / 1_000_000
    ) * pricing["output_per_1m"]
