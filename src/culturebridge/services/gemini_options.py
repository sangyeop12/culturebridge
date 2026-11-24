"""Model-family options for bounded interactive requests."""

import time
from contextlib import contextmanager
from contextvars import ContextVar

from google.genai import types

_request_budget = ContextVar("learning_model_request_budget", default=None)


@contextmanager
def model_request_scope(deadline, stopped):
    token = _request_budget.set({"deadline": deadline, "stopped": stopped, "calls": 0})
    try:
        yield
    finally:
        _request_budget.reset(token)


def interactive_timeout(deadline, maximum_ms, *, attempts=2):
    """Reserve retry time inside the turn budget and check cancellation before each SDK call."""
    budget = _request_budget.get()
    if budget is not None:
        if budget["stopped"]():
            raise ValueError("learning_request_stopped")
        if budget["calls"] >= 12:
            raise ValueError("learning_request_budget")
        deadline = min(deadline, budget["deadline"])
    remaining = int((deadline - time.monotonic()) * 1000) - 1000
    if remaining < 1000:
        raise ValueError("learning_request_budget")
    if budget is not None:
        budget["calls"] += 1
    return max(1, min(maximum_ms, 10000, remaining // attempts))


def interactive_retry():
    """One bounded transient retry; quota/authentication failures stop immediately."""
    return types.HttpRetryOptions(
        attempts=2,
        initial_delay=0.5,
        max_delay=0.5,
        http_status_codes=[500, 502, 503],
    )


def interactive_thinking(model):
    if model.startswith("gemini-2.5-flash"):
        return types.ThinkingConfig(thinking_budget=0)
    if model.startswith("gemini-3"):
        return types.ThinkingConfig(thinking_level="LOW")
    return None
