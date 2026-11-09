# Order State Machine

A service that moves a checkout order through its states and recovers from failures differently depending on where they happen.

## Running it

```bash
pip install ".[dev]"
pytest
uvicorn order_service.api:app --reload   # docs at http://localhost:8000/docs
```

Example run:
To create an order, it expects customer_name, ticket_name, amount.

Create an order:
```
curl -X POST http://127.0.0.1:8000/create-order \
  -H "Content-Type: application/json" \
  -d '{"customer_name": "Alex Kim", "ticket_name": "Knicks vs Celtics", "amount": 125.00}'

{"id":"7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d","customer_name":"Alex Kim","ticket_name":"Knicks vs Celtics","amount":125.0,"state":"initialized","auth_id":null,"history":[{"state":"initialized","at":"2026-11-08T20:49:47.060395+00:00","event":null,"note":""}]}  
```

Advance an order till completion:
```
curl -X POST http://127.0.0.1:8000/orders/7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d/advance 

{"id":"7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d","customer_name":"Alex Kim","ticket_name":"Knicks vs Celtics","amount":125.0,"state":"payment_authorized","auth_id":"auth_e1d5eb5a-02d6-4a40-8de1-62028595caf9","history":[{"state":"initialized","at":"2026-11-08T20:49:47.060395+00:00","event":null,"note":""},{"state":"payment_authorized","at":"2026-11-08T20:50:12.770445+00:00","event":"payment_authorized","note":""}]}

curl -X POST http://127.0.0.1:8000/orders/7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d/advance

{"id":"7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d","customer_name":"Alex Kim","ticket_name":"Knicks vs Celtics","amount":125.0,"state":"complete","auth_id":"auth_e1d5eb5a-02d6-4a40-8de1-62028595caf9","history":[{"state":"initialized","at":"2026-11-08T20:49:47.060395+00:00","event":null,"note":""},{"state":"payment_authorized","at":"2026-11-08T20:50:12.770445+00:00","event":"payment_authorized","note":""},{"state":"complete","at":"2026-11-08T20:50:18.726393+00:00","event":"completed","note":""}]}

curl -X POST http://127.0.0.1:8000/orders/7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d/advance

{"detail":"order is complete, nothing to advance"}%                                                 
```

View history of an order:
```
curl -X GET http://127.0.0.1:8000/orders/7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d 

{"id":"7a2ac7cf-d9dc-49f0-bb16-0734f5fab58d","customer_name":"Alex Kim","ticket_name":"Knicks vs Celtics","amount":125.0,"state":"complete","auth_id":"auth_e1d5eb5a-02d6-4a40-8de1-62028595caf9","history":[{"state":"initialized","at":"2026-11-08T20:49:47.060395+00:00","event":null,"note":""},{"state":"payment_authorized","at":"2026-11-08T20:50:12.770445+00:00","event":"payment_authorized","note":""},{"state":"complete","at":"2026-11-08T20:50:18.726393+00:00","event":"completed","note":""}]}%     
```


## States

```
initialized ──► payment_authorized ──► complete
     │                  │
     ▼                  ▼
  rejected           voiding ──► cancelled
                        │
                        ▼
                  needs_attention
```

- **Payment declined** → `rejected`. Nothing was held on the card, so there's nothing to undo.
- **Completion fails after authorization** → `voiding` → `cancelled`. The card has a hold on it, so we void it.
- **The void also fails** → `needs_attention`. The customer may still have a hold, so this isn't marked as cancelled. It's logged as an error and both failures stay in the history for whoever picks it up.

## API

| | |
|---|---|
| `POST /create-order` | Create an order: `{"customer_name": "Alex Kim", "ticket_name": "Knicks Game", "amount": 125.00}` |
| `POST /orders/{id}/advance` | Run the next step |
| `GET /orders/{id}` | Current state and history |

`advance` runs the next step and the result of that step picks the new state. Clients can't set a state directly, so they can't skip payment or mark a failed void as cancelled.


When running the API, the stub payment gateway and fulfillment fail at random (20% decline, 20% completion failure, 20% void failure), so calling `advance` a few times shows every path. The tests replace the stubs with mocks to force each path deterministically.


## Code

- `state_machine.py`: states, events, the transition table, and the `Order` with its history
- `gateways.py`: payment and fulfillment interfaces, plus random-failure
- `service.py`: what each step does and how each failure is handled
- `api.py`: FastAPI endpoints

## Decisions

- **The service reports events; the state machine picks the state.** The service calls payment and fulfillment, then tells the order what happened (`order.transition(Event.PAYMENT_DECLINED)`). The `TRANSITIONS` table maps `(current state, event)` to the next state, so the whole flow can be read in one place and the service never names a target state. An event that isn't valid in the current state raises `InvalidTransition`.
- **Actions stay in the service.** The state machine has no side effects. Deciding which action to run next (authorize or deliver tickets) and calling external systems is the service's job.


## What I left out

- **Persistence.** Orders live in a dict and are lost on restart.
- **Concurrency.** Two simultaneous `advance` calls (a double tap or a retry from a phone) could both authorize. The fix is adding lock in the database, since an in-process lock wouldn't work across multiple servers.
- **Retries.** A failed void goes straight to `needs_attention` without retrying

## With more time

1. Postgres with a version column on orders to make concurrent updates safe, and history in its own table.
2. Idempotency keys on payment calls and on `advance`, so mobile retries can't double-charge.
3. Treat timeouts as "retryable" rather than "failed": check with the provider before deciding the next state.
4. Retry voids with backoff, and run a background job that picks up orders stuck in `voiding` or `needs_attention`.
5. An ops endpoint to resolve `needs_attention` orders, recorded in the history.
6. Alerts on `needs_attention` instead of just a log line.
