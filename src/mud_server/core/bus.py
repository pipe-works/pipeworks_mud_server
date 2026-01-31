"""
PipeWorks MUD Event Bus

The central nervous system of the MUD server. All significant events flow
through this bus, creating an auditable, replayable record of what happened.

=============================================================================
ARCHITECTURAL PRINCIPLES (see _working/plugin_development.md)
=============================================================================

The bus is boring by design. Boring is how we keep it honest.

1. THE BUS RECORDS FACTS
   - Events represent things that HAPPENED (past tense)
   - "player:move" means the player moved, not "please move the player"
   - The bus does not decide outcomes, it records them

2. EVENTS ARE IMMUTABLE
   - Once emitted, an event cannot be changed
   - This enables replay, debugging, and audit
   - Handlers receive events, they cannot modify them

3. EMIT IS SYNCHRONOUS
   - Event creation and log commit happen synchronously
   - This guarantees deterministic ordering
   - Sequence numbers enforce global order

4. ASYNC IS AN EXECUTION DETAIL
   - Handlers may be sync or async
   - Async handlers are SCHEDULED after the event is committed
   - Async execution does not affect event order

5. PLUGINS REACT, THEY DO NOT INTERVENE
   - There are no "before" events that can block
   - Plugins subscribe and react to facts
   - If a plugin needs to "respond", it emits a NEW event

=============================================================================
GOBLIN LAWS
=============================================================================

Law #7  "No Fat Orcs"     - The bus does ONE thing: record events
Law #8  "Boundary Guards" - Everything flows through the bus first
Law #13 "Guest List"      - Single source of truth, one bus, one log
Law #37 "No Meddling"     - Components communicate via bus, never directly

=============================================================================
USAGE
=============================================================================

    from mud_server.core.bus import bus

    # Emit an event (synchronous - returns immediately after commit)
    event = bus.emit("player:move", {
        "username": "Gribnak",
        "from_room": "tavern",
        "to_room": "street"
    })

    # Subscribe to events
    def on_player_move(event):
        print(f"{event.detail['username']} moved!")

    unsubscribe = bus.on("player:move", on_player_move)

    # Later: stop listening
    unsubscribe()

    # Async handlers work too
    async def on_player_move_async(event):
        await notify_room(event.detail['to_room'])

    bus.on("player:move", on_player_move_async)

=============================================================================
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# TYPE ALIASES
# =============================================================================

# A sync handler takes an event and returns nothing
SyncHandler = Callable[["MudEvent"], None]

# An async handler takes an event and returns a coroutine
AsyncHandler = Callable[["MudEvent"], Coroutine[Any, Any, None]]

# A handler can be either sync or async
EventHandler = SyncHandler | AsyncHandler

# An unsubscribe function takes no args and returns nothing
Unsubscribe = Callable[[], None]


# =============================================================================
# EVENT METADATA
# =============================================================================


@dataclass(frozen=True)
class EventMetadata:
    """
    Metadata attached to every event.

    This metadata provides context for debugging, replay, and audit:
    - timestamp: When did this happen? (wall clock time)
    - source: Which component emitted it? (for debugging)
    - sequence: What's the global order? (for determinism)

    The class is frozen (immutable) because events cannot change after creation.

    Attributes:
        timestamp: Unix epoch milliseconds (UTC). Wall clock time of emission.
                   Used for debugging and display, NOT for ordering.
        source: Name of the component that emitted this event.
                Examples: "engine", "WeatherPlugin", "auth"
        sequence: Monotonically increasing integer. The ONLY reliable way to
                  determine event order. Two events with seq 5 and seq 6 are
                  guaranteed to have been emitted in that order, regardless
                  of timestamp.
    """

    timestamp: int
    source: str
    sequence: int

    @staticmethod
    def create(source: str, sequence: int) -> EventMetadata:
        """
        Factory method to create metadata with current timestamp.

        Args:
            source: The component emitting the event
            sequence: The sequence number (from bus)

        Returns:
            New EventMetadata instance
        """
        # Use UTC to avoid timezone confusion in logs
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        return EventMetadata(timestamp=now_ms, source=source, sequence=sequence)


# =============================================================================
# MUD EVENT
# =============================================================================


@dataclass(frozen=True)
class MudEvent:
    """
    A single event on the bus.

    Events are the atoms of the bus. They represent facts about what happened.
    Once created, they are immutable - this is enforced by frozen=True.

    The event lifecycle:
    1. Engine/plugin calls bus.emit("type", {detail})
    2. Bus creates MudEvent with metadata (sequence number assigned)
    3. Event is appended to the log (COMMITTED - point of no return)
    4. Handlers are notified (sync notification, async execution allowed)
    5. Event is returned to caller

    After step 3, the event is part of history. It cannot be changed.

    Attributes:
        type: The event type string. Convention is "domain:action" format.
              Examples: "player:move", "item:pickup", "chat:message", "tick"
        detail: The event payload. A dictionary of relevant data.
                Should be treated as immutable even though Python doesn't
                enforce this on dict contents.
        _meta: Event metadata (timestamp, source, sequence).
               Named with underscore to indicate it's infrastructure,
               not business data.

    Example:
        MudEvent(
            type="player:move",
            detail={"username": "Gribnak", "from": "tavern", "to": "street"},
            _meta=EventMetadata(timestamp=1706745600000, source="engine", sequence=42)
        )
    """

    type: str
    detail: dict = field(default_factory=dict)
    _meta: EventMetadata | None = field(default=None)

    def __str__(self) -> str:
        """Human-readable representation for logging."""
        if self._meta:
            return (
                f"MudEvent(type='{self.type}', "
                f"source='{self._meta.source}', "
                f"seq={self._meta.sequence})"
            )
        return f"MudEvent(type='{self.type}')"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return f"MudEvent(type={self.type!r}, " f"detail={self.detail!r}, " f"_meta={self._meta!r})"

    @property
    def meta(self) -> EventMetadata | None:
        """
        Public accessor for event metadata.

        Returns the event's metadata (timestamp, source, sequence number).
        The underscore-prefixed _meta is the actual attribute; this property
        provides a cleaner public interface.

        Returns:
            EventMetadata instance, or None if event has no metadata
        """
        return self._meta


# =============================================================================
# MUD BUS (SINGLETON)
# =============================================================================


class MudBus:
    """
    The Central Event Bus - Singleton Pattern.

    There is exactly ONE bus in the system. This is enforced by the singleton
    pattern. All events flow through this single point, creating a unified
    log of everything that happened.

    Why singleton?
    - Single source of truth (Goblin Law #13)
    - All components share the same event history
    - No possibility of events "leaking" to a different bus
    - Simplifies testing (reset_for_testing method)

    Thread Safety:
    - The current implementation is NOT thread-safe
    - This is intentional - the MUD server is single-threaded with async
    - If threading is added later, this class will need locks

    Key Methods:
    - emit(): Record an event (synchronous, returns committed event)
    - on(): Subscribe to an event type (returns unsubscribe function)
    - once(): Subscribe for a single event only
    - wait_for(): Async wait for an event (for coordination)
    - get_event_log(): Retrieve event history (for debugging/replay)

    Example:
        from mud_server.core.bus import bus  # The singleton instance

        # Emit
        bus.emit("player:login", {"username": "Gribnak"})

        # Subscribe
        bus.on("player:login", lambda e: print(f"Welcome {e.detail['username']}"))
    """

    # Singleton state
    _instance: MudBus | None = None
    _initialized: bool = False

    def __new__(cls) -> MudBus:
        """
        Singleton pattern implementation.

        The first call creates the instance. Subsequent calls return
        the same instance. This ensures there is only one bus.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the bus (only runs once due to _initialized flag).

        Sets up:
        - Handler registry (who listens to what)
        - Event log (bounded history)
        - Sequence counter (for ordering)
        - Wait promises (for async coordination)
        """
        # Guard against re-initialization (singleton pattern)
        if MudBus._initialized:
            return

        # =====================================================================
        # HANDLER REGISTRY
        # =====================================================================
        # Maps event_type -> list of handlers
        # Using list (not set) to preserve registration order
        # This makes handler execution order deterministic
        self._handlers: dict[str, list[EventHandler]] = {}

        # =====================================================================
        # EVENT LOG
        # =====================================================================
        # Bounded deque prevents unbounded memory growth (Goblin Law #7)
        # 10,000 events is enough for debugging but won't exhaust memory
        # For persistent history, events should also be written to database
        self._event_log: deque[MudEvent] = deque(maxlen=10000)

        # =====================================================================
        # SEQUENCE COUNTER
        # =====================================================================
        # Monotonically increasing integer
        # This is the ONLY reliable way to determine event order
        # Timestamps can have collisions, sequences cannot
        self._sequence: int = 0

        # =====================================================================
        # WAIT PROMISES
        # =====================================================================
        # For async code that needs to wait for a specific event
        # Maps event_type -> list of futures to resolve
        self._wait_promises: dict[str, list[asyncio.Future[MudEvent]]] = {}

        # =====================================================================
        # DEBUG MODE
        # =====================================================================
        # When True, logs all emit/subscribe/unsubscribe operations
        self.debug: bool = False

        # Mark as initialized
        MudBus._initialized = True
        logger.info("MUD Bus initialized")

    # =========================================================================
    # EMIT (THE CORE OPERATION)
    # =========================================================================

    def emit(
        self, event_type: str, detail: dict[str, Any] | None = None, source: str = "engine"
    ) -> MudEvent:
        """
        Emit an event to the bus.

        THIS IS THE MOST IMPORTANT METHOD IN THE BUS.

        The method is SYNCHRONOUS by design. When it returns:
        1. The event has been created with a sequence number
        2. The event has been committed to the log
        3. All sync handlers have been called
        4. All async handlers have been scheduled

        The event is now part of history. It cannot be changed, suppressed,
        or reordered.

        Args:
            event_type: The type of event (e.g., "player:move", "tick")
                        Convention: "domain:action" format
            detail: The event payload. Optional, defaults to empty dict.
                    Should contain all relevant data for handlers.
            source: Which component is emitting. Defaults to "engine".
                    Used for debugging and filtering.

        Returns:
            The committed MudEvent. This is immutable and now part of
            the event log.

        Example:
            # Simple event
            bus.emit("tick", {"delta": 1.0})

            # Event with details
            event = bus.emit("player:move", {
                "username": "Gribnak",
                "from_room": "tavern",
                "to_room": "street",
                "direction": "north"
            }, source="engine")

            print(event._meta.sequence)  # e.g., 42
        """
        # =====================================================================
        # STEP 1: INCREMENT SEQUENCE (deterministic ordering)
        # =====================================================================
        # This happens FIRST, before anything else
        # The sequence number is the source of truth for event order
        self._sequence += 1
        current_sequence = self._sequence

        # =====================================================================
        # STEP 2: CREATE IMMUTABLE EVENT
        # =====================================================================
        # The event is frozen (immutable) from this point forward
        # detail defaults to empty dict if None
        event = MudEvent(
            type=event_type,
            detail=detail if detail is not None else {},
            _meta=EventMetadata.create(source, current_sequence),
        )

        # =====================================================================
        # STEP 3: COMMIT TO LOG (point of no return)
        # =====================================================================
        # Once this line executes, the event is part of history
        # It will appear in get_event_log() and can never be removed
        self._event_log.append(event)

        if self.debug:
            logger.debug(f"EMIT [{current_sequence}]: {event.type} from {source}")

        # =====================================================================
        # STEP 4: NOTIFY HANDLERS
        # =====================================================================
        # Handlers are notified in registration order (deterministic)
        # Sync handlers execute immediately
        # Async handlers are scheduled for later execution
        self._notify_handlers(event)

        # =====================================================================
        # STEP 5: RESOLVE WAIT PROMISES
        # =====================================================================
        # If any async code is waiting for this event type, resolve their futures
        self._resolve_wait_promises(event)

        # =====================================================================
        # RETURN THE COMMITTED EVENT
        # =====================================================================
        return event

    def _notify_handlers(self, event: MudEvent) -> None:
        """
        Notify all handlers subscribed to this event type.

        Handlers are called in registration order (the order they called on()).
        This makes execution deterministic and predictable.

        Sync handlers:
        - Execute immediately, inline
        - Block until complete
        - Errors are logged but don't affect other handlers

        Async handlers:
        - Scheduled via asyncio.create_task() if a loop is running
        - Otherwise run via asyncio.run() (blocking)
        - The event is already committed - async is just execution

        Args:
            event: The event to deliver to handlers
        """
        # No handlers for this event type? Nothing to do.
        if event.type not in self._handlers:
            return

        # Iterate in registration order
        for handler in self._handlers[event.type]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Async handler - schedule for execution
                    # The event is already committed, this is just execution time
                    self._schedule_async_handler(handler, event)
                else:
                    # Sync handler - execute immediately
                    handler(event)
            except Exception as e:
                # Log the error but continue with other handlers
                # The event is committed regardless of handler errors
                # Handler errors are execution concerns, not logical concerns
                logger.error(f"Handler error for '{event.type}': {e}", exc_info=True)

    def _schedule_async_handler(self, handler: AsyncHandler, event: MudEvent) -> None:
        """
        Schedule an async handler for execution.

        This method handles the complexity of running async code from
        a sync context. Two cases:

        1. Event loop is running (normal server operation):
           Create a task, let it run in the background

        2. No event loop (testing, scripts):
           Run the coroutine synchronously via asyncio.run()

        Args:
            handler: The async handler function
            event: The event to pass to the handler
        """
        try:
            # Try to get the running event loop
            loop = asyncio.get_running_loop()
            # Schedule the handler as a background task
            # We don't await it - it runs when the loop gets to it
            loop.create_task(handler(event))
        except RuntimeError:
            # No running event loop - run synchronously
            # This happens in tests or when called from sync code
            asyncio.run(handler(event))

    def _resolve_wait_promises(self, event: MudEvent) -> None:
        """
        Resolve any futures waiting for this event type.

        This enables the wait_for() method, which allows async code
        to pause until a specific event occurs.

        Args:
            event: The event that just occurred
        """
        if event.type not in self._wait_promises:
            return

        # Resolve all waiting futures
        for future in self._wait_promises[event.type]:
            if not future.done():
                future.set_result(event)

        # Clear the list - these promises are now resolved
        del self._wait_promises[event.type]

    # =========================================================================
    # SUBSCRIBE
    # =========================================================================

    def on(self, event_type: str, handler: EventHandler) -> Unsubscribe:
        """
        Subscribe to an event type.

        When an event of this type is emitted, your handler will be called.
        Handlers are called in registration order (FIFO).

        Remember: You are subscribing to FACTS. The event has already
        happened by the time your handler is called. You are reacting,
        not intervening.

        Args:
            event_type: The event type to listen for (e.g., "player:move")
            handler: Function to call. Can be sync or async.
                     Receives the MudEvent as its only argument.

        Returns:
            An unsubscribe function. Call it to stop receiving events.

        Example:
            # Subscribe
            def on_move(event):
                print(f"{event.detail['username']} moved!")

            unsub = bus.on("player:move", on_move)

            # Later, when done listening:
            unsub()
        """
        # Create handler list for this event type if it doesn't exist
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        # Add handler to the list (preserves order)
        self._handlers[event_type].append(handler)

        if self.debug:
            count = len(self._handlers[event_type])
            logger.debug(f"SUBSCRIBE: '{event_type}' (total handlers: {count})")

        # Return unsubscribe function
        def unsubscribe() -> None:
            """Remove this handler from the subscription list."""
            if event_type in self._handlers:
                try:
                    self._handlers[event_type].remove(handler)
                    if self.debug:
                        logger.debug(f"UNSUBSCRIBE: '{event_type}'")
                except ValueError:
                    # Handler already removed, ignore
                    pass

        return unsubscribe

    def once(self, event_type: str, handler: EventHandler) -> Unsubscribe:
        """
        Subscribe to an event type for a single event only.

        Like on(), but automatically unsubscribes after the first event.
        Useful for one-time initialization or waiting for a specific event.

        Args:
            event_type: The event type to listen for
            handler: Function to call (once)

        Returns:
            An unsubscribe function (in case you want to cancel early)

        Example:
            # Wait for first player to login, then do something
            def on_first_login(event):
                print(f"First player: {event.detail['username']}")
                # Handler automatically unsubscribes after this

            bus.once("player:login", on_first_login)
        """
        # We need to reference unsub before it's defined
        unsub: Unsubscribe | None = None

        def one_time_wrapper(event: MudEvent) -> None:
            """Wrapper that calls handler then unsubscribes."""
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Schedule async handler
                    self._schedule_async_handler(handler, event)
                else:
                    # Call sync handler
                    handler(event)
            finally:
                # Unsubscribe after handling
                if unsub is not None:
                    unsub()

        unsub = self.on(event_type, one_time_wrapper)
        return unsub

    # =========================================================================
    # ASYNC COORDINATION
    # =========================================================================

    async def wait_for(self, event_type: str, timeout_ms: int | None = None) -> MudEvent:
        """
        Wait for a specific event type (async).

        This is for async coordination - waiting until something happens.
        It's an EXECUTION concern, not a LOGICAL concern. The event order
        is not affected by who is waiting.

        Use cases:
        - Wait for server to be ready before sending commands
        - Wait for a resource to be loaded
        - Coordinate between async components

        Args:
            event_type: The event type to wait for
            timeout_ms: Maximum time to wait in milliseconds.
                        None means wait forever.

        Returns:
            The MudEvent when it occurs

        Raises:
            asyncio.TimeoutError: If timeout is reached before event

        Example:
            # Wait for server to be ready
            await bus.wait_for("server:ready", timeout_ms=5000)

            # Now safe to proceed
            bus.emit("player:login", {"username": "Gribnak"})
        """
        # Get the current event loop
        loop = asyncio.get_running_loop()

        # Create a future that will be resolved when the event occurs
        future: asyncio.Future[MudEvent] = loop.create_future()

        # Register the future
        if event_type not in self._wait_promises:
            self._wait_promises[event_type] = []
        self._wait_promises[event_type].append(future)

        # Wait for the future, with optional timeout
        if timeout_ms is not None:
            timeout_sec = timeout_ms / 1000.0
            return await asyncio.wait_for(future, timeout=timeout_sec)
        else:
            return await future

    # =========================================================================
    # EVENT LOG ACCESS
    # =========================================================================

    def get_event_log(self, limit: int | None = None) -> list[MudEvent]:
        """
        Get events from the log.

        The event log is the source of truth for what happened. Events
        are returned in order (oldest first, newest last).

        Use cases:
        - Debugging: "What events led to this state?"
        - Replay: "Reconstruct state from events"
        - Audit: "Who did what when?"

        Args:
            limit: Maximum number of events to return (from the end).
                   None means return all events in the log.

        Returns:
            List of MudEvents in chronological order.

        Example:
            # Get last 10 events
            recent = bus.get_event_log(limit=10)
            for event in recent:
                print(f"[{event._meta.sequence}] {event.type}")

            # Get all events
            all_events = bus.get_event_log()
        """
        if limit is not None:
            # Return the last N events
            return list(self._event_log)[-limit:]
        else:
            # Return all events
            return list(self._event_log)

    def get_sequence(self) -> int:
        """
        Get the current sequence number.

        Useful for debugging and testing. The sequence number is the
        total count of events ever emitted by this bus instance.

        Returns:
            Current sequence number (last assigned)
        """
        return self._sequence

    def get_handler_count(self, event_type: str) -> int:
        """
        Get the number of handlers for an event type.

        Useful for debugging and testing.

        Args:
            event_type: The event type to check

        Returns:
            Number of handlers subscribed to this event type
        """
        if event_type not in self._handlers:
            return 0
        return len(self._handlers[event_type])

    # =========================================================================
    # TESTING SUPPORT
    # =========================================================================

    @classmethod
    def reset_for_testing(cls) -> None:
        """
        Reset the singleton for testing.

        *** NOT FOR PRODUCTION USE ***

        This clears all state and allows a fresh bus to be created.
        Only use this in test setup/teardown.
        """
        cls._instance = None
        cls._initialized = False

    def clear_event_log(self) -> None:
        """
        Clear the event log.

        *** USE WITH CAUTION ***

        This erases event history. Only use for testing or when
        intentionally resetting state.
        """
        self._event_log.clear()
        if self.debug:
            logger.debug("Event log cleared")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

# This is THE bus. Import this, not the class.
# Usage: from mud_server.core.bus import bus
bus = MudBus()
