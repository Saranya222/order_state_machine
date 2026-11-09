from decimal import Decimal

import pytest

from order_state_machine.order_service.state_machine import Event, InvalidTransition, Order, OrderState


def make_order():
    return Order(id="o1", customer_name="Alex Kim", ticket_name="Hamilton", amount=Decimal("99.00"))


def test_new_order_starts_initialized_with_one_history_entry():
    order = make_order()
    assert order.state == OrderState.INITIALIZED
    assert len(order.history) == 1
    assert order.history[0].state == OrderState.INITIALIZED
    assert order.history[0].event is None


@pytest.mark.parametrize("events, expected", [
    ([Event.PAYMENT_AUTHORIZED, Event.COMPLETED], OrderState.COMPLETE),
    ([Event.PAYMENT_DECLINED], OrderState.REJECTED),
    ([Event.PAYMENT_AUTHORIZED, Event.COMPLETION_FAILED, Event.VOIDED], OrderState.CANCELLED),
    ([Event.PAYMENT_AUTHORIZED, Event.COMPLETION_FAILED, Event.VOID_FAILED], OrderState.NEEDS_ATTENTION),
])
def test_state_machine_picks_next_state(events, expected):
    order = make_order()
    for event in events:
        order.transition(event)
    assert order.state == expected
    assert len(order.history) == len(events) + 1


def test_history_records_event_note_and_timestamp():
    order = make_order()
    order.transition(Event.PAYMENT_AUTHORIZED)
    order.transition(Event.COMPLETION_FAILED, "seats no longer available")

    last = order.history[-1]
    assert last.state == OrderState.VOIDING
    assert last.event == Event.COMPLETION_FAILED
    assert last.note == "seats no longer available"
    timestamps = [h.at for h in order.history]
    assert timestamps == sorted(timestamps)


@pytest.mark.parametrize("event", [Event.COMPLETED, Event.VOIDED, Event.COMPLETION_FAILED])
def test_event_not_allowed_in_current_state(event):
    order = make_order()
    with pytest.raises(InvalidTransition):
        order.transition(event)
    # A rejected event changes nothing
    assert order.state == OrderState.INITIALIZED
    assert len(order.history) == 1


def test_terminal_state_accepts_no_events():
    order = make_order()
    order.transition(Event.PAYMENT_DECLINED)
    for event in Event:
        with pytest.raises(InvalidTransition):
            order.transition(event)
