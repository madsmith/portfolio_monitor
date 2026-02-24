from dataclasses import dataclass

import pytest

from portfolio_monitor.core.events import EventBus


@dataclass
class FakeEvent:
    value: int


@dataclass
class OtherEvent:
    name: str


class TestEventBus:
    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, bus):
        """Subscribed handler receives the published event."""
        received = []

        async def handler(event: FakeEvent):
            received.append(event)

        bus.subscribe(FakeEvent, handler)
        await bus.publish(FakeEvent(value=42))

        assert len(received) == 1
        assert received[0].value == 42

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, bus):
        """All subscribers for an event type are called."""
        calls = []

        async def handler_a(event: FakeEvent):
            calls.append("a")

        async def handler_b(event: FakeEvent):
            calls.append("b")

        bus.subscribe(FakeEvent, handler_a)
        bus.subscribe(FakeEvent, handler_b)
        await bus.publish(FakeEvent(value=1))

        assert calls == ["a", "b"]

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """Unsubscribed handler is no longer called."""
        received = []

        async def handler(event: FakeEvent):
            received.append(event)

        bus.subscribe(FakeEvent, handler)
        bus.unsubscribe(FakeEvent, handler)
        await bus.publish(FakeEvent(value=1))

        assert received == []

    @pytest.mark.asyncio
    async def test_unsubscribe_missing_handler(self, bus):
        """Unsubscribing a handler that was never subscribed is a no-op."""
        async def handler(event: FakeEvent):
            pass

        bus.unsubscribe(FakeEvent, handler)

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, bus):
        """Publishing with no subscribers does nothing."""
        await bus.publish(FakeEvent(value=1))

    @pytest.mark.asyncio
    async def test_different_event_types(self, bus):
        """Subscribers only receive events of their subscribed type."""
        fake_received = []
        other_received = []

        async def fake_handler(event: FakeEvent):
            fake_received.append(event)

        async def other_handler(event: OtherEvent):
            other_received.append(event)

        bus.subscribe(FakeEvent, fake_handler)
        bus.subscribe(OtherEvent, other_handler)

        await bus.publish(FakeEvent(value=1))
        await bus.publish(OtherEvent(name="hello"))

        assert len(fake_received) == 1
        assert len(other_received) == 1
        assert fake_received[0].value == 1
        assert other_received[0].name == "hello"

    @pytest.mark.asyncio
    async def test_subscriber_exception_does_not_block_others(self, bus):
        """A failing subscriber doesn't prevent subsequent subscribers from running."""
        calls = []

        async def bad_handler(event: FakeEvent):
            raise RuntimeError("boom")

        async def good_handler(event: FakeEvent):
            calls.append("ok")

        bus.subscribe(FakeEvent, bad_handler)
        bus.subscribe(FakeEvent, good_handler)
        await bus.publish(FakeEvent(value=1))

        assert calls == ["ok"]

    @pytest.mark.asyncio
    async def test_sequential_dispatch_order(self, bus):
        """Subscribers are called in subscription order."""
        order = []

        async def first(event: FakeEvent):
            order.append(1)

        async def second(event: FakeEvent):
            order.append(2)

        async def third(event: FakeEvent):
            order.append(3)

        bus.subscribe(FakeEvent, first)
        bus.subscribe(FakeEvent, second)
        bus.subscribe(FakeEvent, third)
        await bus.publish(FakeEvent(value=0))

        assert order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_unsubscribe_all(self, bus):
        """Unsubscribe_all removes all handlers for an event type."""
        calls = []

        async def handler_a(event: FakeEvent):
            calls.append("a")

        async def handler_b(event: FakeEvent):
            calls.append("b")

        bus.subscribe(FakeEvent, handler_a)
        bus.subscribe(FakeEvent, handler_b)
        bus.unsubscribe_all(FakeEvent)
        await bus.publish(FakeEvent(value=1))

        assert calls == []

    @pytest.mark.asyncio
    async def test_unsubscribe_all_does_not_affect_other_types(self, bus):
        """Unsubscribe_all only removes handlers for the specified type."""
        calls = []

        async def fake_handler(event: FakeEvent):
            calls.append("fake")

        async def other_handler(event: OtherEvent):
            calls.append("other")

        bus.subscribe(FakeEvent, fake_handler)
        bus.subscribe(OtherEvent, other_handler)
        bus.unsubscribe_all(FakeEvent)

        await bus.publish(FakeEvent(value=1))
        await bus.publish(OtherEvent(name="hello"))

        assert calls == ["other"]

    @pytest.mark.asyncio
    async def test_unsubscribe_all_no_subscribers(self, bus):
        """Unsubscribe_all on a type with no subscribers is a no-op."""
        bus.unsubscribe_all(FakeEvent)
