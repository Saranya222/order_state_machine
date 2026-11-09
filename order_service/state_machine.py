from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class OrderState(str, Enum):
    INITIALIZED = "initialized"
    PAYMENT_AUTHORIZED = "payment_authorized"
    COMPLETE = "complete"
    REJECTED = "rejected"
    VOIDING = "voiding"
    CANCELLED = "cancelled"
    NEEDS_ATTENTION = "needs_attention"


class Event(str, Enum):
    """Things that can happen to an order."""
    PAYMENT_AUTHORIZED = "payment_authorized"
    PAYMENT_DECLINED = "payment_declined"
    COMPLETED = "completed"
    COMPLETION_FAILED = "completion_failed"
    VOIDED = "voided"
    VOID_FAILED = "void_failed"


# (current state, event) -> next state. Anything not listed is not allowed.
TRANSITIONS = {
    (OrderState.INITIALIZED, Event.PAYMENT_AUTHORIZED): OrderState.PAYMENT_AUTHORIZED,
    (OrderState.INITIALIZED, Event.PAYMENT_DECLINED): OrderState.REJECTED,
    (OrderState.PAYMENT_AUTHORIZED, Event.COMPLETED): OrderState.COMPLETE,
    (OrderState.PAYMENT_AUTHORIZED, Event.COMPLETION_FAILED): OrderState.VOIDING,
    (OrderState.VOIDING, Event.VOIDED): OrderState.CANCELLED,
    (OrderState.VOIDING, Event.VOID_FAILED): OrderState.NEEDS_ATTENTION,
}


class InvalidTransition(Exception):
    pass


@dataclass
class HistoryEntry:
    state: OrderState
    at: datetime
    event: Event | None = None  # None for the initial entry
    note: str = ""


@dataclass
class Order:
    id: str
    customer_name: str
    ticket_name: str
    amount: Decimal
    state: OrderState = OrderState.INITIALIZED
    auth_id: str | None = None
    history: list[HistoryEntry] = field(default_factory=list)

    def __post_init__(self):
        self.history.append(HistoryEntry(self.state, self._now()))

    def transition(self, event: Event, note: str = "") -> None:
        """Moves to whatever state the transition table says follows this event."""
        next_state = TRANSITIONS.get((self.state, event))
        if next_state is None:
            raise InvalidTransition(f"can't handle {event.value} in state {self.state.value}")
        self.state = next_state
        self.history.append(HistoryEntry(next_state, self._now(), event, note))

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
