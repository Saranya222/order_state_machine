from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from order_state_machine.order_service.api import create_app
from order_state_machine.order_service.gateways import FulfillmentError, PaymentError

ORDER = {"customer_name": "Alex Kim", "ticket_name": "Knicks vs Celtics", "amount": 125.00}


@pytest.fixture
def payment():
    payment = Mock()
    payment.authorize.return_value = "auth_123"
    return payment


@pytest.fixture
def ticket_delivery():
    return Mock()


@pytest.fixture
def client(payment, ticket_delivery):
    return TestClient(create_app(payment, ticket_delivery))


def create_and_advance(client, steps=2):
    order_id = client.post("/create-order", json=ORDER).json()["id"]
    for _ in range(steps):
        client.post(f"/orders/{order_id}/advance")
    return client.get(f"/orders/{order_id}").json()


def test_create_order(client):
    resp = client.post("/create-order", json=ORDER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_name"] == "Alex Kim"
    assert body["ticket_name"] == "Knicks vs Celtics"
    assert body["state"] == "initialized"
    assert len(body["history"]) == 1


def test_happy_path(client):
    order = create_and_advance(client)
    assert order["state"] == "complete"
    assert [h["state"] for h in order["history"]] == ["initialized", "payment_authorized", "complete"]


def test_payment_decline(client, payment):
    payment.authorize.side_effect = PaymentError("card declined")
    assert create_and_advance(client, steps=1)["state"] == "rejected"


def test_completion_failure(client, ticket_delivery):
    ticket_delivery.complete.side_effect = FulfillmentError("seats no longer available")
    assert create_and_advance(client)["state"] == "cancelled"


def test_void_failure(client, payment, ticket_delivery):
    ticket_delivery.complete.side_effect = FulfillmentError("seats no longer available")
    payment.void.side_effect = PaymentError("void error")
    order = create_and_advance(client)
    assert order["state"] == "needs_attention"
    assert order["history"][-1]["note"] == "void error"


def test_advancing_finished_order_returns_409(client, payment):
    payment.authorize.side_effect = PaymentError("card declined")
    order = create_and_advance(client, steps=1)
    assert client.post(f"/orders/{order['id']}/advance").status_code == 409


def test_unknown_order_returns_404(client):
    assert client.get("/orders/nope").status_code == 404
    assert client.post("/orders/nope/advance").status_code == 404