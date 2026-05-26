"""Per-million-token list prices for the Groq models we use.

The free tier we run on bills $0 — these numbers are what the same workload would cost on
Groq's pay-as-you-go plan, surfaced in the dashboard as `estimated_cost_usd` so reviewers
can read the dollar number without us having to fake billing data.

Source: https://groq.com/pricing (verified 2026-05-26).
"""

from __future__ import annotations

# (input $/1M, output $/1M)
GROQ_PRICING: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),  # smallest, used in smoke tests only
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return the pay-as-you-go list-price cost for one chat call.

    Returns 0.0 for models we don't have priced — better to undercount than to invent.
    """
    prices = GROQ_PRICING.get(model)
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return (
        (prompt_tokens / 1_000_000) * input_price
        + (completion_tokens / 1_000_000) * output_price
    )
