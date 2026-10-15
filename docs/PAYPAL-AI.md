# PayPal + AI in UA Market

UA Market is a shop of Ukrainian embroidered clothing and hand-made goods for buyers across
Canada: a Next.js storefront in English and Ukrainian on top of a FastAPI fulfilment core
(inventory ledger, barcode picking, packing, shipping, a courier locker). Before October 2026 it
took payment by Stripe Checkout or Interac e-Transfer and had no AI in it.

For the PayPal AI Hackathon (Devpost, 1 Oct – 12 Nov 2026) it gained three things:

1. **PayPal checkout**, end to end: PayPal JS SDK v6 on the checkout page, the order page and
   inside the concierge; Orders v2 on the server; capture, webhooks, tracking sent back to
   PayPal after shipping, refunds for cancelled orders.
2. **A shopping concierge** (an AI agent) that finds pieces in the real catalogue, keeps to a
   spending limit the buyer sets, and prepares a PayPal checkout. The buyer approves the
   payment in PayPal; the agent cannot place or pay anything.
3. **A PayPal desk** for the owner: an agent in `/admin` that reads the shop and PayPal side by
   side through the **PayPal Agent Toolkit**, finds where they disagree (paid but not shipped,
   shipped without tracking in PayPal, cancelled but not refunded, disputes) and proposes the
   fix as a card the owner confirms.

Everything here runs against the free PayPal **sandbox**. Nothing moves real money.

## Who it is for and the problem

A small diaspora shop sells things people buy for someone else: a vyshyvanka for a
grandchild's first Christmas, a ceramic cup for a mother in Toronto. Buyers ask the same
questions a shopkeeper answers at the counter (which size, what is it made of, what fits in
$150, does it ship to Alberta). The owner, meanwhile, keeps two ledgers in step by hand: the
shop's orders and PayPal's payments, captures, tracking numbers and refunds.

The concierge answers the counter questions from the shop's own data and hands over a
checkout that is already priced, taxed for the province and inside the budget. The desk keeps
the two ledgers in step and leaves every change of money to the owner's click.

## What the agents may do, decided in code

| | Concierge (public) | PayPal desk (owner only) |
|---|---|---|
| Reads | catalogue search, product facts, variant stock, the shop's own quote (shipping, named taxes) | the order queue, one order, PayPal `get_order_details`, `list_disputes`, `get_dispute`, `get_shipment_tracking`, `list_transactions` (PayPal Agent Toolkit) |
| Proposes | a bag card, a checkout card | a refund card, a "send tracking to PayPal" card |
| Never | sets a price, places an order, pays, sees an order key | refunds, pushes tracking or changes anything without Confirm |
| Hard limits | the buyer's spending limit is enforced by `propose_bag` and `prepare_checkout`; a bag over it is refused whatever the model wants | only cancelled PayPal orders are refundable; only shipped orders with a tracking number get tracking pushed |
| Proof | the trace line under every answer lists the tools it called | same trace, with the toolkit method names |

The model chooses SKUs and quantities. Prices, shipping and tax come from `app/services/storefront.py:quote`, the
same function the checkout page uses, so the concierge's total and the checkout's total are
the same number (tested in `tests/test_paypal.py`).

## The PayPal flow

```
buyer ── PayPal button (JS SDK v6, web component) ──┐ click
                                                    │ createOrder promise:
                                                    │   POST /api/order        → shop order AWAITING_PAYMENT, stock held
                                                    │   POST /api/order/N/paypal → Orders v2 create, priced from DB
                                                    ▼
                                  PayPal popup: buyer signs in and approves
                                                    │ onApprove
                                                    ▼
             POST /api/order/N/paypal/capture → Orders v2 capture → amount and currency must equal the order total
                                                    │ exact match only
                                                    ▼
                                      order PAID, goods reserved, "paid" email
                                                    │ … pick, pack, ship with tracking …
                                                    ▼
                         Orders v2 /track: carrier + tracking number go to PayPal (seller protection)
```

- `app/services/paypal.py`: OAuth token cache; `build_order_request` (items with SKU, item_total,
  shipping, tax_total, `custom_id` = shop order id, `invoice_id` = order number,
  `shipping_preference: SET_PROVIDED_ADDRESS`, because tax was computed for that province);
  `create_for` (reuses a live PayPal order instead of opening a second one); `capture_for`
  (idempotent, handles `ORDER_ALREADY_CAPTURED`, `INSTRUMENT_DECLINED`); `apply_capture` (a
  capture for any other amount opens a `PAYMENT_AMOUNT_MISMATCH` problem and the order stays
  unpaid; `PENDING` waits for the webhook); `push_tracking` (carrier names mapped to PayPal's
  codes, `OTHER` + name otherwise); `refund`; `verify_webhook` (PayPal's
  verify-webhook-signature API); `apply_webhook_event` (`CHECKOUT.ORDER.APPROVED` captures an
  order whose buyer closed the page, `PAYMENT.CAPTURE.COMPLETED` pays a pending one,
  `DENIED`/`REVERSED` open a problem for the owner); `sync_pending_tracking` (the five-minute
  timer retries tracking PayPal did not take).
- `web/components/PayPalButton.tsx`: loads `https://www.sandbox.paypal.com/web-sdk/v6/core` once,
  `createInstance({clientId, components: ["paypal-payments"]})`, `findEligibleMethods`,
  `createPayPalOneTimePaymentSession`, and starts the session inside the click with a promise for
  the order id (so the popup is not blocked).
- Demo orders (placeholder catalogue) can be paid only in the sandbox; the API refuses to start
  with sandbox credentials once the catalogue is declared live.

## AI

- Model: any OpenAI-compatible `/chat/completions` endpoint with tool calling
  (`app/services/llm.py`). The hosted demo uses **gpt-oss:120b on Ollama Cloud**. A local Ollama
  (`qwen3:30b`) works with `AI_BASE_URL=http://localhost:11434/v1`.
- PayPal Agent Toolkit: `paypal-agent-toolkit` 1.11.0 (Python). The desk uses its framework-free
  `PayPalAPI.run(method, params)` with the shop's sandbox credentials, so tool names and payloads are
  PayPal's own. It is installed with `--no-deps` (Dockerfile) because only the shared module is used.
- Development: the code was written with Claude Code (Anthropic) as the coding agent. Claude is
  not part of the running product.

## Run it yourself

1. A free PayPal sandbox app: https://developer.paypal.com/dashboard/applications/sandbox
   (Create App, Merchant, any sandbox business account; tick **Transaction search** for the desk's
   transaction list). Copy the client id and secret.
2. An OpenAI-compatible model with tool calling: an Ollama Cloud key, or a local Ollama.
3. Then:

```bash
git clone https://github.com/ctmakc/uamarket-paypal && cd uamarket-paypal
cp .env.example .env
# fill PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, AI_API_KEY (or AI_BASE_URL for a local model),
# and the admin sign-in: python3 tools/admin_password_hash.py  (prints two lines for .env), ADMIN_API_KEY=<any long string>
docker compose up --build
curl -X POST -H "x-api-key: $ADMIN_API_KEY" http://localhost:8000/admin/seed-catalog
```

Storefront http://localhost:3000 (press **Ask the concierge**), admin http://localhost:3000/admin
(**PayPal desk** in the top bar). Pay with any sandbox *personal* account from your developer
dashboard.

Without Docker: see the main README ("Without Docker"); add the PayPal and AI variables to the
API's environment.

Tests: `pytest tests/test_paypal.py` runs the PayPal flow against a mock PayPal and the agents
against a scripted model (20 tests); the whole backend suite is `pytest -q`.

## Hosted demo

https://uamarket-paypal.agintent.com, PayPal sandbox, demonstration catalogue. To pay, sign in to
the PayPal window with the sandbox buyer below (test money only):

- email: listed in the Devpost submission's testing instructions
- password: listed in the Devpost submission's testing instructions

## What changed during the hackathon

Everything in this document. The baseline commit of this repository is the shop as it stood on
17 September 2026 (storefront, fulfilment core, Stripe and e-Transfer, no PayPal, no AI); every
later commit is hackathon work. `git diff <baseline>..HEAD --stat` shows the size of it.

## Honest limits

- The catalogue is a demonstration one: the makers are invented and the photos are generated;
  every page says so.
- The concierge ships only to Canadian addresses and does not offer locker pickup.
- PayPal's transaction search lags new payments by a few hours, so the desk's transaction list can
  be behind the shop.
- Pay Later and Venmo buttons are not wired; the SDK session is the plain PayPal one-time payment.
