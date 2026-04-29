from collections import defaultdict
from collections.abc import Awaitable, Callable

from portfolio_monitor.utils import get_trace_logger

logger = get_trace_logger(__name__)

type EventHandler[T] = Callable[[T], Awaitable[None]]


class EventBus:
    """In-process async pub/sub event bus with typed events.

    Subscribe to event classes, publish event instances. Subscribers
    are awaited sequentially to preserve ordering.
    """

    def __init__(self) -> None:
        self._subscribers: defaultdict[type, list[EventHandler]] = defaultdict(list)

    def subscribe[T](self, event_type: type[T], handler: EventHandler[T]) -> None:
        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed %s to %s", handler, event_type.__name__)

    def unsubscribe[T](self, event_type: type[T], handler: EventHandler[T]) -> None:
        try:
            self._subscribers[event_type].remove(handler)
            logger.debug("Unsubscribed %s from %s", handler, event_type.__name__)
        except ValueError:
            pass

    def unsubscribe_all(self, event_type: type) -> None:
        self._subscribers.pop(event_type, None)
        logger.debug("Unsubscribed all handlers from %s", event_type.__name__)

    async def publish(self, event: object) -> None:
        event_type: type = type(event)
        handlers: list[EventHandler] = self._subscribers[event_type]
        logger.trace("Publishing %s to %d handler(s)", event_type.__name__, len(handlers))
        for handler in handlers:
            try:
                logger.trace("  -> %s", handler)
                await handler(event)
            except Exception:
                logger.exception(
                    "Error in event handler %s for %s",
                    handler,
                    event_type.__name__,
                )
