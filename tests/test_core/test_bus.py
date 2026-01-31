"""
Tests for the MUD Event Bus

These tests verify the core architectural constraints:

1. Events are immutable after creation
2. Emit is synchronous (event committed before return)
3. Event ordering is deterministic (sequence numbers)
4. Handlers are called in registration order
5. Async handlers are scheduled, not awaited inline
6. The bus is a singleton

See _working/plugin_development.md for architectural details.
"""

import asyncio

import pytest

from mud_server.core.bus import EventMetadata, MudBus, MudEvent, bus
from mud_server.core.events import Events, get_all_event_types, is_valid_event_type

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_bus():
    """
    Reset the bus singleton before and after each test.

    This ensures tests are isolated and don't affect each other.
    The autouse=True means this runs for every test automatically.
    """
    MudBus.reset_for_testing()
    yield
    MudBus.reset_for_testing()


@pytest.fixture
def test_bus():
    """
    Provide a fresh bus instance for testing.

    Since we reset the singleton in reset_bus, this creates a new bus.
    """
    return MudBus()


# =============================================================================
# EVENT METADATA TESTS
# =============================================================================


class TestEventMetadata:
    """Tests for EventMetadata class."""

    @pytest.mark.unit
    def test_create_metadata(self):
        """EventMetadata.create() should populate all fields."""
        meta = EventMetadata.create(source="test", sequence=42)

        assert meta.source == "test"
        assert meta.sequence == 42
        assert meta.timestamp > 0  # Should be a valid timestamp

    @pytest.mark.unit
    def test_metadata_is_immutable(self):
        """EventMetadata should be immutable (frozen dataclass)."""
        meta = EventMetadata.create(source="test", sequence=1)

        # Attempting to modify should raise an error
        with pytest.raises(AttributeError):
            meta.source = "modified"  # type: ignore

        with pytest.raises(AttributeError):
            meta.sequence = 999  # type: ignore


# =============================================================================
# MUD EVENT TESTS
# =============================================================================


class TestMudEvent:
    """Tests for MudEvent class."""

    @pytest.mark.unit
    def test_create_event(self):
        """MudEvent should store type and detail."""
        event = MudEvent(
            type="test:event", detail={"key": "value"}, _meta=EventMetadata.create("test", 1)
        )

        assert event.type == "test:event"
        assert event.detail == {"key": "value"}
        assert event._meta is not None
        assert event._meta.sequence == 1

    @pytest.mark.unit
    def test_event_is_immutable(self):
        """MudEvent should be immutable (frozen dataclass)."""
        event = MudEvent(
            type="test:event", detail={"key": "value"}, _meta=EventMetadata.create("test", 1)
        )

        # Attempting to modify should raise an error
        with pytest.raises(AttributeError):
            event.type = "modified"  # type: ignore

    @pytest.mark.unit
    def test_event_str_representation(self):
        """MudEvent __str__ should be human-readable."""
        event = MudEvent(type="player:moved", detail={}, _meta=EventMetadata.create("engine", 42))

        string = str(event)
        assert "player:moved" in string
        assert "engine" in string
        assert "42" in string

    @pytest.mark.unit
    def test_event_default_detail(self):
        """MudEvent should default to empty dict for detail."""
        event = MudEvent(type="test:event")

        assert event.detail == {}


# =============================================================================
# BUS SINGLETON TESTS
# =============================================================================


class TestBusSingleton:
    """Tests for the singleton pattern."""

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        """Multiple MudBus() calls should return the same instance."""
        bus1 = MudBus()
        bus2 = MudBus()

        assert bus1 is bus2

    @pytest.mark.unit
    def test_global_bus_was_singleton_at_import(self):
        """
        The global 'bus' was the singleton when the module was imported.

        Note: After reset_for_testing(), the global 'bus' is stale - it
        references the old instance. New MudBus() calls create a new instance.
        This is expected behavior for testing. In production, reset is never called.
        """
        # After reset (from fixture), MudBus() creates a new instance
        local_bus = MudBus()

        # The global 'bus' was created at import time (before reset)
        # So they are different after reset - this is correct for testing
        # In production (no reset), they would be the same
        assert bus is not local_bus  # Different after reset

        # But two new calls should return the same instance
        another_bus = MudBus()
        assert local_bus is another_bus

    @pytest.mark.unit
    def test_reset_for_testing_creates_new_instance(self):
        """reset_for_testing should allow a new instance to be created."""
        bus1 = MudBus()
        bus1.emit("test:event")

        MudBus.reset_for_testing()

        bus2 = MudBus()

        # Should be different instances
        assert bus1 is not bus2
        # New instance should have empty log
        assert len(bus2.get_event_log()) == 0


# =============================================================================
# EMIT TESTS
# =============================================================================


class TestEmit:
    """Tests for the emit() method."""

    @pytest.mark.unit
    def test_emit_returns_event(self, test_bus):
        """emit() should return the committed event."""
        event = test_bus.emit("test:event", {"key": "value"})

        assert isinstance(event, MudEvent)
        assert event.type == "test:event"
        assert event.detail == {"key": "value"}

    @pytest.mark.unit
    def test_emit_assigns_sequence_number(self, test_bus):
        """emit() should assign monotonically increasing sequence numbers."""
        event1 = test_bus.emit("test:first")
        event2 = test_bus.emit("test:second")
        event3 = test_bus.emit("test:third")

        assert event1._meta.sequence == 1
        assert event2._meta.sequence == 2
        assert event3._meta.sequence == 3

    @pytest.mark.unit
    def test_emit_adds_to_log(self, test_bus):
        """emit() should add events to the event log."""
        test_bus.emit("test:one")
        test_bus.emit("test:two")

        log = test_bus.get_event_log()

        assert len(log) == 2
        assert log[0].type == "test:one"
        assert log[1].type == "test:two"

    @pytest.mark.unit
    def test_emit_with_source(self, test_bus):
        """emit() should record the source component."""
        event = test_bus.emit("test:event", source="WeatherPlugin")

        assert event._meta.source == "WeatherPlugin"

    @pytest.mark.unit
    def test_emit_default_source(self, test_bus):
        """emit() should default source to 'engine'."""
        event = test_bus.emit("test:event")

        assert event._meta.source == "engine"

    @pytest.mark.unit
    def test_emit_with_none_detail(self, test_bus):
        """emit() should handle None detail gracefully."""
        event = test_bus.emit("test:event", None)

        assert event.detail == {}

    @pytest.mark.unit
    def test_emit_is_synchronous(self, test_bus):
        """emit() should be synchronous - event in log immediately after call."""
        # Before emit, log should be empty
        assert len(test_bus.get_event_log()) == 0

        # Emit
        event = test_bus.emit("test:event")

        # Immediately after, event should be in log
        log = test_bus.get_event_log()
        assert len(log) == 1
        assert log[0] is event


# =============================================================================
# SUBSCRIBE TESTS
# =============================================================================


class TestSubscribe:
    """Tests for the on() method."""

    @pytest.mark.unit
    def test_on_receives_events(self, test_bus):
        """Handlers should receive emitted events."""
        received = []

        def handler(event):
            received.append(event)

        test_bus.on("test:event", handler)
        test_bus.emit("test:event", {"key": "value"})

        assert len(received) == 1
        assert received[0].type == "test:event"
        assert received[0].detail == {"key": "value"}

    @pytest.mark.unit
    def test_on_only_receives_matching_events(self, test_bus):
        """Handlers should only receive events of the subscribed type."""
        received = []

        def handler(event):
            received.append(event)

        test_bus.on("test:target", handler)
        test_bus.emit("test:other")
        test_bus.emit("test:target")
        test_bus.emit("test:another")

        assert len(received) == 1
        assert received[0].type == "test:target"

    @pytest.mark.unit
    def test_on_returns_unsubscribe_function(self, test_bus):
        """on() should return a function that unsubscribes the handler."""
        received = []

        def handler(event):
            received.append(event)

        unsub = test_bus.on("test:event", handler)

        # Should receive this
        test_bus.emit("test:event")
        assert len(received) == 1

        # Unsubscribe
        unsub()

        # Should NOT receive this
        test_bus.emit("test:event")
        assert len(received) == 1  # Still 1, not 2

    @pytest.mark.unit
    def test_multiple_handlers_same_event(self, test_bus):
        """Multiple handlers can subscribe to the same event type."""
        results = []

        def handler1(event):
            results.append("handler1")

        def handler2(event):
            results.append("handler2")

        test_bus.on("test:event", handler1)
        test_bus.on("test:event", handler2)
        test_bus.emit("test:event")

        assert results == ["handler1", "handler2"]

    @pytest.mark.unit
    def test_handlers_called_in_registration_order(self, test_bus):
        """Handlers should be called in the order they were registered."""
        order = []

        for i in range(5):

            def make_handler(n):
                def handler(event):
                    order.append(n)

                return handler

            test_bus.on("test:event", make_handler(i))

        test_bus.emit("test:event")

        assert order == [0, 1, 2, 3, 4]

    @pytest.mark.unit
    def test_handler_error_does_not_affect_other_handlers(self, test_bus):
        """If one handler raises, other handlers should still be called."""
        results = []

        def handler1(event):
            results.append("handler1")

        def bad_handler(event):
            raise ValueError("Intentional error")

        def handler2(event):
            results.append("handler2")

        test_bus.on("test:event", handler1)
        test_bus.on("test:event", bad_handler)
        test_bus.on("test:event", handler2)

        # Should not raise, and both good handlers should run
        test_bus.emit("test:event")

        assert results == ["handler1", "handler2"]


# =============================================================================
# ONCE TESTS
# =============================================================================


class TestOnce:
    """Tests for the once() method."""

    @pytest.mark.unit
    def test_once_receives_first_event(self, test_bus):
        """once() handler should receive the first matching event."""
        received = []

        def handler(event):
            received.append(event)

        test_bus.once("test:event", handler)
        test_bus.emit("test:event", {"n": 1})

        assert len(received) == 1
        assert received[0].detail == {"n": 1}

    @pytest.mark.unit
    def test_once_only_receives_once(self, test_bus):
        """once() handler should only be called once."""
        received = []

        def handler(event):
            received.append(event)

        test_bus.once("test:event", handler)
        test_bus.emit("test:event", {"n": 1})
        test_bus.emit("test:event", {"n": 2})
        test_bus.emit("test:event", {"n": 3})

        # Should only have received the first one
        assert len(received) == 1
        assert received[0].detail == {"n": 1}

    @pytest.mark.unit
    def test_once_can_be_cancelled(self, test_bus):
        """once() should return an unsubscribe function for early cancellation."""
        received = []

        def handler(event):
            received.append(event)

        unsub = test_bus.once("test:event", handler)

        # Cancel before any events
        unsub()

        # Should not receive anything
        test_bus.emit("test:event")
        assert len(received) == 0


# =============================================================================
# ASYNC HANDLER TESTS
# =============================================================================


class TestAsyncHandlers:
    """Tests for async handler support."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_handler_is_scheduled(self, test_bus):
        """Async handlers should be scheduled for execution."""
        received = []

        async def async_handler(event):
            received.append(event)

        test_bus.on("test:event", async_handler)
        test_bus.emit("test:event")

        # Give the async task time to run
        await asyncio.sleep(0.01)

        assert len(received) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_handler_error_logged_not_raised(self, test_bus):
        """Async handler errors should be logged, not raised."""

        async def bad_async_handler(event):
            raise ValueError("Async error")

        test_bus.on("test:event", bad_async_handler)

        # Should not raise
        test_bus.emit("test:event")

        # Give it time to run
        await asyncio.sleep(0.01)


# =============================================================================
# WAIT_FOR TESTS
# =============================================================================


class TestWaitFor:
    """Tests for the wait_for() method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_wait_for_resolves_on_event(self, test_bus):
        """wait_for() should resolve when the event is emitted."""

        async def emit_later():
            await asyncio.sleep(0.01)
            test_bus.emit("test:event", {"key": "value"})

        # Start emitting in background
        asyncio.create_task(emit_later())

        # Wait for the event
        event = await test_bus.wait_for("test:event", timeout_ms=1000)

        assert event.type == "test:event"
        assert event.detail == {"key": "value"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_wait_for_timeout(self, test_bus):
        """wait_for() should raise TimeoutError if event doesn't arrive."""
        with pytest.raises(asyncio.TimeoutError):
            await test_bus.wait_for("never:happens", timeout_ms=50)


# =============================================================================
# EVENT LOG TESTS
# =============================================================================


class TestEventLog:
    """Tests for event log functionality."""

    @pytest.mark.unit
    def test_get_event_log_returns_all_events(self, test_bus):
        """get_event_log() should return all events."""
        test_bus.emit("test:one")
        test_bus.emit("test:two")
        test_bus.emit("test:three")

        log = test_bus.get_event_log()

        assert len(log) == 3

    @pytest.mark.unit
    def test_get_event_log_with_limit(self, test_bus):
        """get_event_log(limit=N) should return last N events."""
        for i in range(10):
            test_bus.emit("test:event", {"n": i})

        log = test_bus.get_event_log(limit=3)

        assert len(log) == 3
        # Should be the last 3 events
        assert log[0].detail == {"n": 7}
        assert log[1].detail == {"n": 8}
        assert log[2].detail == {"n": 9}

    @pytest.mark.unit
    def test_event_log_preserves_order(self, test_bus):
        """Event log should preserve chronological order."""
        test_bus.emit("test:first")
        test_bus.emit("test:second")
        test_bus.emit("test:third")

        log = test_bus.get_event_log()

        assert log[0].type == "test:first"
        assert log[1].type == "test:second"
        assert log[2].type == "test:third"

    @pytest.mark.unit
    def test_clear_event_log(self, test_bus):
        """clear_event_log() should remove all events."""
        test_bus.emit("test:event")
        test_bus.emit("test:event")

        assert len(test_bus.get_event_log()) == 2

        test_bus.clear_event_log()

        assert len(test_bus.get_event_log()) == 0

    @pytest.mark.unit
    def test_event_log_bounded(self):
        """Event log should be bounded to prevent memory issues."""
        # Create a bus with default maxlen (10000)
        test_bus = MudBus()

        # The log is bounded - we can't easily test 10000 events,
        # but we can verify the deque has a maxlen
        assert test_bus._event_log.maxlen == 10000


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================


class TestGetSequence:
    """Tests for get_sequence() method."""

    @pytest.mark.unit
    def test_get_sequence_starts_at_zero(self, test_bus):
        """Sequence should start at 0 before any events."""
        assert test_bus.get_sequence() == 0

    @pytest.mark.unit
    def test_get_sequence_increments(self, test_bus):
        """Sequence should increment with each emit."""
        assert test_bus.get_sequence() == 0

        test_bus.emit("test:one")
        assert test_bus.get_sequence() == 1

        test_bus.emit("test:two")
        assert test_bus.get_sequence() == 2


class TestGetHandlerCount:
    """Tests for get_handler_count() method."""

    @pytest.mark.unit
    def test_handler_count_starts_at_zero(self, test_bus):
        """Handler count should be 0 for unsubscribed event types."""
        assert test_bus.get_handler_count("test:event") == 0

    @pytest.mark.unit
    def test_handler_count_increments(self, test_bus):
        """Handler count should increment with subscriptions."""
        test_bus.on("test:event", lambda e: None)
        assert test_bus.get_handler_count("test:event") == 1

        test_bus.on("test:event", lambda e: None)
        assert test_bus.get_handler_count("test:event") == 2

    @pytest.mark.unit
    def test_handler_count_decrements_on_unsub(self, test_bus):
        """Handler count should decrement when unsubscribing."""
        unsub = test_bus.on("test:event", lambda e: None)
        assert test_bus.get_handler_count("test:event") == 1

        unsub()
        assert test_bus.get_handler_count("test:event") == 0


# =============================================================================
# EVENTS MODULE TESTS
# =============================================================================


class TestEventsModule:
    """Tests for the events.py module."""

    @pytest.mark.unit
    def test_events_constants_are_strings(self):
        """Event constants should be strings."""
        assert isinstance(Events.PLAYER_MOVED, str)
        assert isinstance(Events.TICK, str)
        assert isinstance(Events.CHAT_SAID, str)

    @pytest.mark.unit
    def test_events_follow_naming_convention(self):
        """Event constants should follow 'domain:action' format."""
        # Check a sampling of events
        assert ":" in Events.PLAYER_MOVED
        assert ":" in Events.ITEM_PICKED_UP
        assert ":" in Events.CHAT_SAID

        # Tick is a special case
        assert Events.TICK == "tick"

    @pytest.mark.unit
    def test_is_valid_event_type(self):
        """is_valid_event_type should identify standard events."""
        assert is_valid_event_type(Events.PLAYER_MOVED) is True
        assert is_valid_event_type(Events.TICK) is True
        assert is_valid_event_type("custom:event") is False

    @pytest.mark.unit
    def test_get_all_event_types(self):
        """get_all_event_types should return all standard event types."""
        all_events = get_all_event_types()

        assert len(all_events) > 0
        assert Events.PLAYER_MOVED in all_events
        assert Events.TICK in all_events


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestBusIntegration:
    """Integration tests for realistic usage scenarios."""

    @pytest.mark.unit
    def test_typical_game_flow(self, test_bus):
        """Test a typical game flow with multiple events."""
        events_received = []

        def track_events(event):
            events_received.append(event.type)

        # Subscribe to multiple event types
        test_bus.on(Events.PLAYER_LOGGED_IN, track_events)
        test_bus.on(Events.PLAYER_MOVED, track_events)
        test_bus.on(Events.CHAT_SAID, track_events)

        # Simulate a game session
        test_bus.emit(Events.PLAYER_LOGGED_IN, {"username": "Gribnak", "room": "spawn"})
        test_bus.emit(
            Events.PLAYER_MOVED, {"username": "Gribnak", "from_room": "spawn", "to_room": "tavern"}
        )
        test_bus.emit(
            Events.CHAT_SAID, {"username": "Gribnak", "message": "Hello!", "room": "tavern"}
        )

        assert events_received == [Events.PLAYER_LOGGED_IN, Events.PLAYER_MOVED, Events.CHAT_SAID]

    @pytest.mark.unit
    def test_event_replay_capability(self, test_bus):
        """Events in the log should be replayable."""
        # Emit some events
        test_bus.emit("player:moved", {"username": "A", "room": "tavern"})
        test_bus.emit("player:moved", {"username": "B", "room": "street"})
        test_bus.emit("player:moved", {"username": "A", "room": "street"})

        # Get the log
        log = test_bus.get_event_log()

        # "Replay" - reconstruct state from events
        player_rooms = {}
        for event in log:
            if event.type == "player:moved":
                player_rooms[event.detail["username"]] = event.detail["room"]

        # Final state should be correct
        assert player_rooms == {"A": "street", "B": "street"}
