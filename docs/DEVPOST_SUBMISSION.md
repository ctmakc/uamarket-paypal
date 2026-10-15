# Devpost submission package — PayPal AI Hackathon 2026

> **Status:** DRAFT / NOT SUBMITTED. This is editable submission copy and a verification checklist, not evidence that the project is entered or ready for judging.
> Deadline from official rules: **November 12, 2026, 12:00 pm PST (3:00 pm EST in Ottawa)**.
> Devpost competition: https://paypalaihackathon.devpost.com/
> Existing project: https://github.com/ctmakc/uamarket-paypal
> Demo URL (deployment health verified 2026-10-15, payment flow **not** yet verified): https://uamarket-paypal.agintent.com/

## Project title

**UA Market — Your AI Shopkeeper, With PayPal in Charge of the Money**

## Tagline

An AI shopping concierge that understands what you need and prepares a real PayPal checkout; a second AI agent helps small merchants reconcile payments, tracking and refunds without giving autonomous agents control of funds.

## Problem and audience

Independent merchants cannot afford to staff an expert shop assistant around the clock, and buyers often shop with constraints that conventional filters cannot express: an occasion, recipient, size, delivery location and a hard budget. After each order, the merchant must reconcile store order state with the payment processor, shipment tracking and refund/dispute lifecycle. Automation that can spend or refund without an explicit approval is unacceptable.

Our concrete example is a bilingual Canadian shop for Ukrainian heritage gifts and apparel. The catalogue on the hackathon demo is *clearly labelled sample data*; makers and products in the demo are fictional.

## Solution (draft for Devpost description)

UA Market introduces two practical AI agents around a deterministic order-and-payment core.

**1. Buyer-side shopping concierge.** The agent searches real catalogue records and inventory, discusses gifts and sizing in natural language, observes the shopper's spending ceiling, and prepares a checkout card. The order quote — items, taxes, shipping, total — is computed by the store backend, not invented by the LLM. The shopper must explicitly accept the terms and authorize the payment through PayPal. The agent cannot pay or order autonomously.

**2. Merchant-side PayPal desk.** A second agent compares store order events with PayPal order, transaction, tracking and dispute state via the PayPal Agent Toolkit. It highlights discrepancies and proposes a specific action: send tracking for a shipped order, or initiate a refund for a cancelled eligible order. Execution requires an authenticated owner's explicit confirmation. The rules for permissible actions live in the server, not only the prompt.

**3. Full payment lifecycle.** The backend integrates PayPal Orders v2, sandbox checkout/capture, verification of amounts/currency, verified webhooks, shipping tracking and refund workflows. These payment invariants are deterministic, auditable and protected against duplicate updates.

The result is an explainable, human-authorized agentic commerce flow, rather than a chatbot taped onto a checkout button.

## PayPal and AI technologies

- PayPal developer platform (sandbox), Orders v2, capture, webhook verification, tracking and refund operations.
- PayPal JS SDK v6 with explicit buyer payment approval.
- PayPal Agent Toolkit 1.11.0 (Python, framework-free PayPalAPI methods) for merchant-side reconciliation.
- AI: OpenAI-compatible tool-calling model service. Project docs specify gpt-oss:120b on Ollama Cloud for the hosted demo; local Qwen via Ollama also supported.
- Next.js 16 / TypeScript storefront; FastAPI / Python backend with an order, inventory and fulfilment system.
- Automated tests: `pytest tests/test_paypal.py` (repo documents 20 PayPal-related unit/integration-style tests against mocks); full backend: `pytest -q`.

## What changed during this hackathon

Baseline before October 2026: the existing UA Market storefront, inventory/fulfilment core, Stripe and Interac e-Transfer. Significant changes after October 1 include PayPal payments and the PayPal-focused concierge and operator agents. The current implementation history and detailed architecture are recorded in `docs/PAYPAL-AI.md`. Show commit-by-commit evidence in final submission; do not claim changes not backed by Git history.

## Links to include in entry

- Code: https://github.com/ctmakc/uamarket-paypal
- Technical project documentation: https://github.com/ctmakc/uamarket-paypal/blob/main/docs/PAYPAL-AI.md
- Demo: https://uamarket-paypal.agintent.com/
- Video: **TODO — public YouTube URL (<3 minutes); not recorded/uploaded yet**
- Screenshots: **TODO — capture actual working checkout and PayPal desk, not mocks**

## Demo video outline (target 2:40)

- **0:00–0:18** — One buyer question and one merchant reconciliation problem; explain who needs this.
- **0:18–0:55** — Shopper asks for an embroidered gift below CAD 150. Show AI searches, real product details and the enforced budget.
- **0:55–1:30** — Agent prepares an exact quote. Buyer manually accepts and completes PayPal **sandbox** approval. Show the same amount on the order receipt.
- **1:30–2:10** — Merchant signs into PayPal desk; agent spots a tracking/refund discrepancy, cites PayPal toolkit calls and proposes action. Owner explicitly approves one safe action.
- **2:10–2:33** — Show verified webhook/updated order and a PayPal event, highlight idempotency and human authorization.
- **2:33–2:40** — Differentiator and target users; URL and repo.
- Do not film or claim sections that do not function in a verified sandbox deployment.

## Submission / QA gates (mandatory before entering)

- [x] Registration confirmed by Devpost email dated October 3, 2026.
- [x] Public GitHub repository exists with MIT open-source license.
- [x] Documentation and source claim central PayPal + AI integration.
- [x] Public demo page opens and has an AI concierge entry point (browser check October 15, 2026).
- [ ] **Critical: deployment still displays "No payment method is switched on" on homepage (observed October 15). Diagnose environment/feature flags and enable the sandbox-only PayPal demo; do not enable live real-money payments.**
- [ ] Prove browser end-to-end buyer flow with PayPal sandbox personal account and exact capture amount.
- [ ] Prove AI tool-calling is actually configured on hosted demo (not merely a visible concierge widget).
- [ ] Prove merchant PayPal desk is usable with judge-accessible sandbox account and that its safeguards work.
- [ ] Run tests against a fresh checkout; capture actual pass/fail logs with commit SHA.
- [ ] Arrange short-lived judge demo credentials/instructions securely through the Devpost entry; never commit secrets, actual client IDs or passwords.
- [ ] Confirm storefront, backend, screenshot and README are current relative to deploy.
- [ ] Film and upload an original public YouTube demo shorter than 3 minutes.
- [ ] Populate and save the actual Devpost submission draft, attach video and screenshots.
- [ ] Final manual review that the judges can run or use every advertised feature.
- [ ] Submit before November 12, 12:00 pm PST and verify published Devpost entry URL.

## Potential prize positioning

Primary: Best Use of PayPal + AI / Best Use of Agentic Commerce.
Additional: Most Impactful / Best Demo Delivery; overall awards.
The prizes are judged, not guaranteed. Avoid adding optional sponsor tools merely for checkboxes unless they demonstrably improve functionality.

## Follow-on candidate (separate, substantially different entry)

**FinDep** (`ctmakc/findep`): AI-native accounts payable and finance control room. Its current repository documents intake, invoice extraction, duplicate detection, multilevel approval and locked payment schedules; it does **not** yet demonstrate PayPal integration. A distinct entry might introduce PayPal sandbox invoice-payment collection, webhook reconciliation and a risk/evidence-aware agent. Treat this as a prospective scope, not a working PayPal feature. Prepare only if first submission is independently judge-ready.

## Sources

- Official competition rules: https://paypalaihackathon.devpost.com/rules
- Architecture/implementation reference: `docs/PAYPAL-AI.md`
- Demo verification: logged-in Chrome text inspection on 2026-10-15
