"""Model-family options for bounded interactive requests."""

from google.genai import types


def interactive_retry():
    """Initial request plus five retries for retryable provider failures."""
    return types.HttpRetryOptions(
        attempts=6,
        initial_delay=0.5,
        max_delay=2.0,
        http_status_codes=[429, 500, 502, 503, 504],
    )


def interactive_thinking(model):
    if model.startswith("gemini-2.5-flash"):
        return types.ThinkingConfig(thinking_budget=0)
    if model.startswith("gemini-3"):
        return types.ThinkingConfig(thinking_level="LOW")
    return None
