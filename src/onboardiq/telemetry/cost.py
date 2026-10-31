"""Model token cost estimation for OnboardIQ telemetry.

Per docs/06_IMPLEMENTATION_PLAN.md T12.
"""

from __future__ import annotations

# Pricing table: USD per 1M tokens (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-1.5-flash": (0.075, 0.30),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-haiku": (0.80, 4.00),
    "default": (0.15, 0.60),
}


def estimate_cost(
    model_name: str = "default",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> float:
    """Calculate estimated cost in USD based on model token counts."""
    pricing = MODEL_PRICING.get(model_name.lower(), MODEL_PRICING["default"])
    input_rate, output_rate = pricing
    cost = (prompt_tokens / 1_000_000.0 * input_rate) + (
        completion_tokens / 1_000_000.0 * output_rate
    )
    return round(cost, 6)

