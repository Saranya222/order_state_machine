import logging
import uuid
from decimal import Decimal

from order_state_machine.order_service.gateways import FakeTicketDelivery, FulfillmentError, PaymentError, FakePaymentGateway
from order_state_machine.order_service.state_machine import Event, InvalidTransition, Order, OrderState

log = logging.getLogger(__name__)


class OrderNotFound(Exception):
    pass


class OrderService:
    def __init__(self, payment: FakePaymentGateway, ticketDelivery: FakeTicketDelivery):
        self.payment = payment
        self.ticketDelivery = ticketDelivery
        self.orders: dict[str, Order] = {}

    def create(self, customer_name: str, ticket_name: str, amount: Decimal) -> Order:
        """create an order and store it in memory dictionary using a generated ID"""
        order = Order(
            id=str(uuid.uuid4()),
            customer_name=customer_name,
            ticket_name=ticket_name,
            amount=amount,
        )
        self.orders[order.id] = order
        return order

    def get(self, order_id: str) -> Order:
        """Get order details from dictionary using order id"""
        if order_id not in self.orders:
            raise OrderNotFound(order_id)
        return self.orders[order_id]

    def advance(self, order_id: str) -> Order:
        """Runs the next step and reports what happened to the state machine."""
        order = self.get(order_id)
        if order.state == OrderState.INITIALIZED:
            self._authorize(order)
        elif order.state == OrderState.PAYMENT_AUTHORIZED:
            self._complete(order)
        else:
            raise InvalidTransition(f"order is {order.state.value}, nothing to advance")
        return order

    def _authorize(self, order: Order) -> None:
        try:
            auth_id = self.payment.authorize(order)
            order.auth_id = auth_id
            order.transition(Event.PAYMENT_AUTHORIZED)
        except PaymentError as e:
            # Payment failed so nothing was held on the customers card, so there's nothing to clean up.
            order.transition(Event.PAYMENT_DECLINED)

    def _complete(self, order: Order) -> None:
        try:
            self.ticketDelivery.complete(order)
            order.transition(Event.COMPLETED)
        except FulfillmentError as e:
            # Money is held on the card, so it has to be released. Start voiding process
            order.transition(Event.COMPLETION_FAILED, str(e))
            self._void(order)

    def _void(self, order: Order) -> None:
        try:
            self.payment.void(order)
            order.transition(Event.VOIDED)
        except PaymentError as e:
            # Void also failed - Don't mark it cancelled: the customer may still have a hold on their card.
            order.transition(Event.VOID_FAILED, str(e))
            log.error("order %s needs attention, auth %s may still be held", order.id, order.auth_id)
            
