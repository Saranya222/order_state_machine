import random
import uuid
from typing import Protocol


class PaymentError(Exception):
    pass


class FulfillmentError(Exception):
    pass


class PaymentGateway(Protocol):
    def authorize(self, order) -> str:
        """Returns an authorization id. Raises PaymentError if declined."""

    def void(self, order) -> None:
        """Releases the hold on the card. Raises PaymentError if it fails."""


class TicketDelivery(Protocol):
    def complete(self, order) -> None:
        """Sends the tickets to the customer. Raises FulfillmentError if it fails."""


# Stubs used when running the API. They fail at random so every path
# shows up when trying it by hand. Tests use mocks instead.

class FakePaymentGateway(PaymentGateway):
    def __init__(self, decline_rate: float = 0.2, void_failure_rate: float = 0.2):
        self.decline_rate = decline_rate
        self.void_failure_rate = void_failure_rate

    def authorize(self, order) -> str:
        if random.random() < self.decline_rate:
            raise PaymentError("Payment authorization error")
        return f"auth_{uuid.uuid4()}"

    def void(self, order) -> None:
        if random.random() < self.void_failure_rate:
            raise PaymentError("Void failed")


class FakeTicketDelivery(TicketDelivery):
    def __init__(self, failure_rate: float = 0.2):
        self.failure_rate = failure_rate

    def complete(self, order) -> None:
        if random.random() < self.failure_rate:
            raise FulfillmentError("Error getting ticket to customer")