import logging
from typing import Any

# Define TRACE level below DEBUG
TRACE = logging.DEBUG // 2
logging.addLevelName(TRACE, "TRACE")


class TraceAdapter(logging.LoggerAdapter):
    """LoggerAdapter that adds a .trace() convenience method."""

    def __init__(self, logger: logging.Logger):
        super().__init__(logger, extra={})

    def trace(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self.logger.log(TRACE, msg, *args, **kwargs)


def get_trace_logger(name: str) -> TraceAdapter:
    """Return a TraceAdapter wrapping the manager-provided logger."""
    return TraceAdapter(logging.getLogger(name))
