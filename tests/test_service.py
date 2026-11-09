from decimal import Decimal
from unittest.mock import Mock

import pytest

from order_state_machine.order_service.gateways import FulfillmentError, PaymentError
from order_state_machine.order_service.service import OrderNotFound, OrderService
from order_state_machine.order_service.state_machine import Event, InvalidTransition, OrderState as S


@pytest.fixture
def payment():
    payment = Mock()
    payment.authorize.return_value = "auth_123"  # approve by default
    return payment


@pytest.fixture
def ticket_delivery():
    return Mock()  # complete() succeeds by default


@pytest.fixture
def service(payment, ticket_delivery):
    return OrderService(payment, ticket_delivery)


def new_order(service):
    return service.create("Alex Kim", "Knicks vs Celtics, Sec 102", Decimal("125.00"))


def states(order):
    return [h.state for h in order.history]


def test_create_stores_order(service):
    order = new_order(service)
    assert service.get(order.id) is order
    assert order.customer_name == "Alex Kim"
    assert order.amount == Decimal("125.00")
    assert order.state == S.INITIALIZED


def test_happy_path(service, payment, ticket_delivery):
    order = new_order(service)
    service.advance(order.id)
    service.advance(order.id)

    assert states(order) == [S.INITIALIZED, S.PAYMENT_AUTHORIZED, S.COMPLETE]
    assert order.auth_id == "auth_123"
    ticket_delivery.complete.assert_called_once_with(order)
    payment.void.assert_not_called()


def test_payment_decline(service, payment, ticket_delivery):
    payment.authorize.side_effect = PaymentError("card declined")
    order = new_order(service)
    service.advance(order.id)

    assert states(order) == [S.INITIALIZED, S.REJECTED]
    assert order.auth_id is None
    ticket_delivery.complete.assert_not_called()
    payment.void.assert_not_called()


def test_completion_failure_voids_and_cancels(service, payment, ticket_delivery):
    ticket_delivery.complete.side_effect = FulfillmentError("seats no longer available")
    order = new_order(service)
    service.advance(order.id)
    service.advance(order.id)

    assert states(order) == [S.INITIALIZED, S.PAYMENT_AUTHORIZED, S.VOIDING, S.CANCELLED]
    payment.void.assert_called_once_with(order)


def test_completion_failure_and_void_failure_needs_attention(service, payment, ticket_delivery):
    ticket_delivery.complete.side_effect = FulfillmentError("seats no longer available")
    payment.void.side_effect = PaymentError("void failed")
    order = new_order(service)
    service.advance(order.id)
    service.advance(order.id)

    assert states(order) == [S.INITIALIZED, S.PAYMENT_AUTHORIZED, S.VOIDING, S.NEEDS_ATTENTION]
    # Both failures are kept in the history, not just the last one
    assert order.history[2].event == Event.COMPLETION_FAILED
    assert order.history[2].note == "seats no longer available"
    assert order.history[3].event == Event.VOID_FAILED
    assert order.history[3].note == "void failed"