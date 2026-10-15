"""The shopping agent on the storefront ("Concierge").

It finds pieces in the real catalogue, puts together a bag inside the buyer's budget, and
prepares a PayPal checkout. What it may do is decided here, in code, not in the prompt:

- every fact it can repeat comes from a tool reading the database (titles, makers,
  materials, prices, stock); the prompt forbids anything else and the tools return nothing
  else;
- it chooses SKUs and quantities only; prices, shipping and tax are computed by the shop's
  own quote code, exactly as the checkout page computes them;
- a spending limit the buyer sets in the chat panel is a hard cap: a bag over it is refused
  by `propose_bag` and `prepare_checkout`, whatever the model wants;
- it cannot place or pay an order. `prepare_checkout` returns a card; the buyer ticks the
  terms box and presses the PayPal button, the browser places the order through the same
  endpoint the checkout page uses, and money moves only after the buyer approves in PayPal.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from . import llm, paypal
from .catalog import CatalogError, get_product, list_categories, list_products
from .storefront import (
    PROVINCES, StorefrontError, catalogue_live, excluded_provinces, find_order_by_token, order_view, quote,
    storefront_config,
)

MAX_HISTORY = 16
MAX_MESSAGE_CHARS = 1200
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,80}$")
POSTAL_RE = re.compile(r"^[A-Za-z]\d[A-Za-z] ?\d[A-Za-z]\d$")


def system_prompt(locale: str, budget: float | None, bag: list[dict] | None = None) -> str:
    cfg = storefront_config()
    pickup = "Locker pickup is available." if cfg["pickup"]["enabled"] else "Locker pickup is not offered on this deployment; every order ships."
    demo = ("This deployment shows a DEMONSTRATION catalogue: the makers and pieces are made-up examples and the "
            "photos are generated. If asked, say so plainly. Payments run in the PayPal sandbox: test money only.") \
        if not catalogue_live() else ""
    budget_line = f"The buyer set a spending limit of CA${budget:.2f} for this conversation (goods + shipping, before tax). " \
                  "The tools enforce it." if budget else "No spending limit is set; ask for one when the buyer mentions a gift or a budget."
    lang = "Ukrainian" if locale == "uk" else "English"
    bag_line = ""
    if bag:
        bag_line = "\nThe bag card on the buyer's screen right now: " + "; ".join(
            f"{b['qty']} x {b['sku']}" for b in bag) + ". Use these SKUs unless the buyer changes their mind.\n"
    return f"""You are the shopping concierge of UA Market, an online shop of Ukrainian embroidered clothing and hand-made goods that ships across Canada (prices in CAD). {demo}

Your job: understand who the buyer is shopping for, find fitting pieces with the tools, propose a bag, and prepare a PayPal checkout when the buyer is ready. Show before you ask: on a broad request, search first and name two or three fitting pieces with prices, then ask at most one short question (size, colour, or which one).

Rules you never break:
1. Every fact about a product (name, maker, region, material, technique, care, price, availability) must come from a tool result in this conversation. If a tool did not say it, you do not know it. Never invent reviews, ratings, delivery dates, discounts or stock counts.
2. You pick SKUs and quantities. The shop prices everything. Quote prices exactly as the tools return them, in CAD.
3. {budget_line}
4. You cannot pay and you cannot place orders. When the buyer wants to buy, collect: email, full name, and the Canadian shipping address (street, city, province code, postal code). As soon as you have them, call prepare_checkout without asking for another confirmation: the card it shows is the confirmation step. The buyer finishes by ticking the terms box and pressing the PayPal button on the card; PayPal asks for their approval. Never ask for card numbers or PayPal passwords.
5. Never say an order is paid unless order_status says it is.
6. For clothing, ask the size and, when there is more than one, the colour before proposing, unless the buyer already said them. Never pick a colour or size for the buyer. Use the variant labels from get_product.
7. {pickup} Shipping is a flat fee with free shipping over a threshold (the quote tools return the numbers). Excluded provinces: {", ".join(excluded_provinces()) or "none"}.
{bag_line}8. Always answer in the language of the buyer's last message (Ukrainian or English); the shop's interface language is {lang}. Keep each answer under 90 words, plain sentences, no markdown tables. Mention at most 3 products per answer; the panel shows cards for the products you name, so do not paste URLs.
"""


@dataclass
class Session_:
    db: Session
    locale: str = "en"
    budget: float | None = None
    orders: list[dict] = field(default_factory=list)  # [{order_number, token}] placed from this chat
    cards: list[dict] = field(default_factory=list)


def _clip(text: str | None, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _compact(item: dict, lang: str) -> dict:
    uk = lang == "uk"
    return {
        "slug": item["slug"],
        "title": item["title_uk"] if uk and item.get("title_uk") else item["title"],
        "category": item.get("category"),
        "maker": ((item.get("maker") or {}).get("name_uk" if uk else "name")),
        "region": ((item.get("maker") or {}).get("region_uk" if uk else "region")),
        "origin": item.get("origin_label_uk" if uk else "origin_label"),
        "price_from_cad": item.get("price_from_cad"),
        "price_to_cad": item.get("price_to_cad"),
        "in_stock": item.get("in_stock"),
    }


def _card_item(item: dict) -> dict:
    return {
        "slug": item["slug"], "title": item["title"], "title_uk": item.get("title_uk"),
        "maker": (item.get("maker") or {}).get("name"), "maker_uk": (item.get("maker") or {}).get("name_uk"),
        "price_from_cad": item.get("price_from_cad"), "price_to_cad": item.get("price_to_cad"),
        "image_url": item.get("image_url"), "in_stock": item.get("in_stock"),
        "origin": item.get("origin"), "origin_label": item.get("origin_label"), "origin_label_uk": item.get("origin_label_uk"),
    }


def _add_products_card(s: Session_, items: list[dict]) -> None:
    for card in s.cards:
        if card["type"] == "products":
            known = {i["slug"] for i in card["items"]}
            card["items"].extend(_card_item(i) for i in items if i["slug"] not in known)
            return
    if items:
        s.cards.append({"type": "products", "items": [_card_item(i) for i in items]})


# --------------------------------------------------------------------------- tools

def _tools(s: Session_) -> list[llm.Tool]:
    categories = [c["slug"] for c in list_categories(s.db)]

    def search_catalogue(args: dict) -> dict:
        q = _clip(str(args.get("query") or ""), 80) or None
        cat = args.get("category") if args.get("category") in categories else None
        lo = args.get("min_price_cad")
        hi = args.get("max_price_cad")
        limit = max(1, min(int(args.get("limit") or 6), 8))
        in_stock = bool(args.get("in_stock_only", True))
        found = list_products(s.db, category=cat, q=q, in_stock=in_stock or None, limit=60)["items"]
        if not found and q:
            # A phrase the search did not match whole: try its longest words one by one.
            for word in sorted(re.findall(r"\w{4,}", q), key=len, reverse=True)[:3]:
                found = list_products(s.db, category=cat, q=word, in_stock=in_stock or None, limit=60)["items"]
                if found:
                    break
        if lo is not None:
            found = [i for i in found if (i.get("price_to_cad") or 0) >= float(lo)]
        if hi is not None:
            found = [i for i in found if (i.get("price_from_cad") or 0) <= float(hi)]
        found = found[:limit]
        _add_products_card(s, found)
        return {"count": len(found), "items": [_compact(i, s.locale) for i in found],
                "note": "Only these pieces match. Prices are CAD." if found else "Nothing matches. Try a broader query or another category."}

    def get_product_tool(args: dict) -> dict:
        slug = str(args.get("slug") or "").strip()
        try:
            p = get_product(s.db, slug)
        except CatalogError:
            return {"error": f"No product with slug {slug}. Use search_catalogue to find slugs."}
        uk = s.locale == "uk"
        pick = (lambda en, ua: (p.get(ua) or p.get(en)) if uk else p.get(en))
        variants = [{"sku": v["sku"], "label": (v.get("label_uk") if uk else v.get("label")) or v.get("label"),
                     "price_cad": v["price_cad"], "in_stock": v["availability"]["in_stock"]} for v in p["variants"]]
        _add_products_card(s, [p])
        return {
            "slug": p["slug"], "title": pick("title", "title_uk"), "subtitle": pick("subtitle", "subtitle_uk"),
            "maker": (p.get("maker") or {}).get("name_uk" if uk else "name"),
            "region": (p.get("maker") or {}).get("region_uk" if uk else "region"),
            "origin": pick("origin_label", "origin_label_uk"), "origin_note": pick("origin_note", "origin_note_uk"),
            "description": _clip(pick("description", "description_uk"), 420),
            "technique": pick("technique", "technique_uk"), "material": pick("material", "material_uk"),
            "care": _clip(pick("care", "care_uk"), 200),
            "variants": variants,
        }

    def _priced(lines: list[dict], province: str | None) -> tuple[dict | None, dict | None]:
        clean = []
        for line in lines or []:
            sku = str(line.get("sku") or "").strip().upper()
            try:
                qty = int(line.get("qty") or line.get("quantity") or 1)
            except (TypeError, ValueError):
                qty = 1
            if not SKU_RE.match(sku) or not 1 <= qty <= 5:
                return None, {"error": f"Bad line {line}: use SKUs from get_product and quantities 1-5."}
            clean.append({"sku": sku, "qty": qty})
        if not clean:
            return None, {"error": "The bag is empty."}
        if len(clean) > 8:
            return None, {"error": "At most 8 lines in one bag."}
        q = quote(s.db, lines=clean, fulfillment_method="SHIP", province=province)
        problems = [l for l in q["lines"] if l.get("status") != "ok"]
        if problems:
            return None, {"error": "Some lines cannot be sent as asked.",
                          "lines": [{"sku": l["sku"], "status": l.get("status"), "max_qty": l.get("max_qty")} for l in problems]}
        return q, None

    def _budget_check(q: dict, asked: float | None) -> dict | None:
        caps = [b for b in (s.budget, asked) if b]
        if not caps:
            return None
        cap = min(caps)
        spend = round(q["subtotal_cad"] + q["shipping_cad"], 2)
        if spend > cap + 0.004:
            return {"error": f"Over the spending limit: goods + shipping come to CA${spend:.2f}, the limit is CA${cap:.2f}. "
                             "Propose something cheaper or ask the buyer to raise the limit."}
        return None

    def _lines_out(q: dict) -> list[dict]:
        return [{"sku": l["sku"], "qty": l["qty"], "title": l.get("title"), "title_uk": l.get("title_uk"),
                 "label": l.get("label"), "label_uk": l.get("label_uk"), "maker": l.get("maker"), "maker_uk": l.get("maker_uk"),
                 "unit_price_cad": l.get("unit_price_cad"), "image_url": l.get("image_url"), "slug": l.get("slug")}
                for l in q["lines"]]

    def propose_bag(args: dict) -> dict:
        q, err = _priced(args.get("lines") or [], None)
        if err:
            return err
        over = _budget_check(q, args.get("budget_cad"))
        if over:
            return over
        card = {"type": "bag", "lines": _lines_out(q), "subtotal_cad": q["subtotal_cad"], "shipping_cad": q["shipping_cad"],
                "free_over_cad": storefront_config()["shipping"]["free_over_cad"], "budget_cad": s.budget or args.get("budget_cad"),
                "note": _clip(str(args.get("why") or ""), 200)}
        s.cards = [c for c in s.cards if c["type"] != "bag"] + [card]
        return {"ok": True, "subtotal_cad": q["subtotal_cad"], "shipping_cad": q["shipping_cad"],
                "tax": "computed at checkout from the province",
                "shown_to_buyer": "A bag card with these lines and an 'Add to bag' button."}

    def prepare_checkout(args: dict) -> dict:
        ship = dict(args.get("ship_to") or {})
        # Models name the street line several ways; all of them mean the same field.
        for alias in ("street", "address", "address_line_1", "address1", "line1"):
            if not ship.get("street1") and ship.get(alias):
                ship["street1"] = ship[alias]
        for want, aliases in (("postal_code", ("postal", "postcode", "zip")), ("province", ("province_code", "state", "region")),
                              ("street2", ("unit", "apt", "address_line_2"))):
            for alias in aliases:
                if not ship.get(want) and ship.get(alias):
                    ship[want] = ship[alias]
        province = str(ship.get("province") or "").strip().upper()
        email = str(args.get("email") or "").strip().lower()
        name = str(args.get("name") or "").strip()
        missing = []
        if "@" not in email or "." not in email.split("@")[-1]:
            missing.append("email")
        if len(name) < 2:
            missing.append("name")
        for key in ("street1", "city", "postal_code"):
            if not str(ship.get(key) or "").strip():
                missing.append(f"ship_to.{key}")
        if province not in PROVINCES:
            missing.append("ship_to.province (two-letter code, e.g. ON)")
        if ship.get("postal_code") and not POSTAL_RE.match(str(ship["postal_code"]).strip()):
            missing.append("ship_to.postal_code (format A1A 1A1)")
        if missing:
            return {"error": "Ask the buyer for: " + ", ".join(missing)}
        if province in excluded_provinces():
            return {"error": f"The shop does not ship to {province} yet; tell the buyer."}
        q, err = _priced(args.get("lines") or [], province)
        if err:
            return err
        over = _budget_check(q, args.get("budget_cad"))
        if over:
            return over
        if not paypal.configured():
            return {"error": "PayPal is not configured on this shop; the buyer can use the checkout page instead."}
        pc = str(ship["postal_code"]).strip().upper().replace(" ", "")
        card = {
            "type": "checkout", "payment_method": "PAYPAL", "sandbox": paypal.sandbox(),
            "lines": _lines_out(q),
            "totals": {k: q[k] for k in ("subtotal_cad", "shipping_cad", "tax_cad", "tax_rate", "tax_lines", "total_cad")},
            "contact": {"email": email, "name": name, "phone": None},
            "ship_to": {"name": name, "street1": str(ship.get("street1")).strip(), "street2": (str(ship.get("street2") or "").strip() or None),
                        "city": str(ship.get("city")).strip(), "province": province, "postal_code": f"{pc[:3]} {pc[3:]}", "country": "CA"},
            "demo": not catalogue_live(),
        }
        s.cards = [c for c in s.cards if c["type"] not in {"checkout", "bag"}] + [card]
        return {"ok": True, "total_cad": q["total_cad"], "tax_cad": q["tax_cad"], "shipping_cad": q["shipping_cad"],
                "shown_to_buyer": "A checkout card with the lines, the totals, a terms checkbox and the PayPal button. "
                                  "The order is placed and paid only when the buyer presses it and approves in PayPal."}

    def order_status(args: dict) -> dict:
        number = str(args.get("order_number") or "").strip().upper()
        known = {o.get("order_number", "").upper(): o.get("token") for o in s.orders}
        if number not in known:
            return {"error": "Only orders placed from this conversation can be looked up here; the buyer can use the order page."}
        try:
            order = find_order_by_token(s.db, number, known[number] or "")
        except StorefrontError:
            return {"error": "Order not found."}
        view = order_view(s.db, order)
        s.cards.append({"type": "order", "order_number": number, "status": view["status"], "paid_at": view["paid_at"],
                        "total_cad": view["totals"]["total_cad"], "payment": view["payment"]})
        return {"order_number": number, "status": view["status"]["label"], "paid": view["paid_at"] is not None,
                "total_cad": view["totals"]["total_cad"], "payment_method": view["payment"].get("method")}

    line_schema = {"type": "array", "items": {"type": "object", "properties": {
        "sku": {"type": "string", "description": "Variant SKU from get_product"},
        "qty": {"type": "integer", "minimum": 1, "maximum": 5}}, "required": ["sku", "qty"]}}
    return [
        llm.Tool("search_catalogue", "Search the shop's catalogue (English or Ukrainian words). Returns slugs, titles, makers, CAD price ranges, stock.",
                 {"type": "object", "properties": {
                     "query": {"type": "string", "description": "Words such as 'linen shirt', 'вишиванка', 'ceramic mug'"},
                     "category": {"type": "string", "enum": categories},
                     "min_price_cad": {"type": "number"}, "max_price_cad": {"type": "number"},
                     "in_stock_only": {"type": "boolean", "default": True},
                     "limit": {"type": "integer", "minimum": 1, "maximum": 8}}}, search_catalogue),
        llm.Tool("get_product", "Full facts for one product: maker, origin, material, technique, care, and every variant with its SKU, label, price and stock.",
                 {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]}, get_product_tool),
        llm.Tool("propose_bag", "Show the buyer a proposed bag (SKUs + quantities). The shop prices it and checks stock and the spending limit.",
                 {"type": "object", "properties": {"lines": line_schema, "budget_cad": {"type": "number"},
                                                    "why": {"type": "string", "description": "One sentence: why these pieces"}},
                  "required": ["lines"]}, propose_bag),
        llm.Tool("prepare_checkout", "Prepare a PayPal checkout card for the buyer once they gave email, name and a Canadian shipping address. Does not place or pay the order.",
                 {"type": "object", "properties": {
                     "lines": line_schema, "email": {"type": "string"}, "name": {"type": "string"},
                     "ship_to": {"type": "object", "properties": {
                         "street1": {"type": "string"}, "street2": {"type": "string"}, "city": {"type": "string"},
                         "province": {"type": "string", "description": "Two-letter code: ON, QC, BC, AB, ..."},
                         "postal_code": {"type": "string"}}, "required": ["street1", "city", "province", "postal_code"]},
                     "budget_cad": {"type": "number"}}, "required": ["lines", "email", "name", "ship_to"]}, prepare_checkout),
        llm.Tool("order_status", "Status of an order the buyer placed from this conversation (paid or not, total).",
                 {"type": "object", "properties": {"order_number": {"type": "string"}}, "required": ["order_number"]}, order_status),
    ]


def _history(messages: list[dict]) -> list[dict]:
    out = []
    for m in (messages or [])[-MAX_HISTORY:]:
        role = m.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = _clip(str(m.get("content") or ""), MAX_MESSAGE_CHARS)
        if content:
            out.append({"role": role, "content": content})
    if not out or out[-1]["role"] != "user":
        raise ValueError("The last message must come from the buyer")
    return out


def chat(db: Session, *, messages: list[dict], locale: str = "en", budget_cad: float | None = None,
         orders: list[dict] | None = None, bag: list[dict] | None = None) -> dict:
    budget = float(budget_cad) if budget_cad else None
    if budget is not None and not 5 <= budget <= 5000:
        budget = None
    s = Session_(db=db, locale="uk" if locale == "uk" else "en", budget=budget, orders=list(orders or [])[:10])
    clean_bag = []
    for line in (bag or [])[:8]:
        sku = str(line.get("sku") or "").strip().upper()
        if SKU_RE.match(sku):
            clean_bag.append({"sku": sku, "qty": max(1, min(int(line.get("qty") or 1), 5))})
    turn = llm.run(system_prompt(s.locale, budget, clean_bag), _history(messages), _tools(s),
                   max_rounds=int(os.getenv("AI_MAX_TOOL_ROUNDS") or 6))
    # Product cards only for pieces the answer actually names (the model may have looked at more).
    reply = turn.reply
    for card in s.cards:
        if card["type"] == "products":
            named = [i for i in card["items"] if i["title"].lower() in reply.lower() or (i.get("title_uk") or "").lower() in reply.lower()]
            card["items"] = (named or card["items"])[:4]
    return {"reply": reply, "cards": s.cards, "trace": turn.trace, "budget_cad": budget,
            "model": llm.model(), "sandbox": paypal.sandbox()}
