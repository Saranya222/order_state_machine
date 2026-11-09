from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from order_state_machine.order_service.gateways import FakeTicketDelivery, FakePaymentGateway
from order_state_machine.order_service.service import OrderNotFound, OrderService
from order_state_machine.order_service.state_machine import InvalidTransition


class CreateOrder(BaseModel):
    customer_name: str
    ticket_name: str
    amount: Decimal


def create_app(payment=None, ticket_delivery=None) -> FastAPI:
    service = OrderService(payment, ticket_delivery)
    app = FastAPI(title="Order State Machine")

    @app.post("/create-order")
    def create_order(body: CreateOrder):
        return service.create(body.customer_name, body.ticket_name, body.amount)

    @app.post("/orders/{order_id}/advance")
    def advance(order_id: str):
        try:
            return service.advance(order_id)
        except OrderNotFound:
            raise HTTPException(404, "order not found")
        except InvalidTransition as e:
            raise HTTPException(409, str(e))

    @app.get("/orders/{order_id}")
    def get_order(order_id: str):
        try:
            return service.get(order_id)
        except OrderNotFound:
            raise HTTPException(404, "order not found")

    return app


app = create_app(FakePaymentGateway(), FakeTicketDelivery())
