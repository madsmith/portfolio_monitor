from typing import Any

from opentelemetry import trace as otel_trace


def logfire_set_attribute(key: str, value: Any) -> None:
    """Set an attribute on the currently active logfire/OTel span."""
    otel_trace.get_current_span().set_attribute(key, value)
