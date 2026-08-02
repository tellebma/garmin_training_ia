"""Versioned USD/1M-token pricing per OpenAI model — updated by hand on price changes.

Dernière vérification des tarifs : 2026-08-03 (https://developers.openai.com/api/docs/pricing).
Le cached input (~10 % du prix input sur les familles 5.x) n'est pas modélisé ici : on
sur-compte légèrement l'input, ce qui est le sens sûr pour un suivi de coût.
"""

from __future__ import annotations

MODEL_PRICING: dict[str, dict[str, float]] = {
    # Modèle par défaut depuis le passage à la famille 5.6 : prix input au niveau de
    # gpt-4o-mini, ~3,75x moins cher que gpt-5.4-mini sur une génération type.
    "gpt-5.6-luna": {"input_per_1m": 0.20, "output_per_1m": 1.20},
    "gpt-5.6-terra": {"input_per_1m": 2.00, "output_per_1m": 12.00},
    "gpt-5.6-sol": {"input_per_1m": 5.00, "output_per_1m": 30.00},
    "gpt-5.4-nano": {"input_per_1m": 0.20, "output_per_1m": 1.25},
    # Défaut précédent (fix #124), gardé pour le coût des générations historiques.
    "gpt-5.4-mini": {"input_per_1m": 0.75, "output_per_1m": 4.50},
    "gpt-5.4": {"input_per_1m": 2.50, "output_per_1m": 15.00},
    "gpt-5-nano": {"input_per_1m": 0.05, "output_per_1m": 0.40},
    "gpt-5-mini": {"input_per_1m": 0.25, "output_per_1m": 2.00},
    "gpt-5": {"input_per_1m": 1.25, "output_per_1m": 10.00},
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
