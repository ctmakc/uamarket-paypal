"""Transactional email for storefront orders — standard library only, no SDK.

Everything is read from the environment at send time, the same way the rest of the
storefront reads its configuration:

    SMTP_HOST                 hostname of the SMTP server. Empty = the service is disabled.
    SMTP_PORT                 default 587 (or 465 when SMTP_SECURITY=ssl)
    SMTP_USER                 login, optional (some relays authenticate by IP)
    SMTP_PASSWORD             password for that login, optional. Never logged.
    SMTP_SECURITY             starttls (default) | ssl | none
    SMTP_TIMEOUT_SECONDS      socket timeout, default 15
    MAIL_FROM                 From header, e.g. "UA Market <shop@example.com>". Empty = disabled.
    MAIL_REPLY_TO             Reply-To header. Defaults to SHOP_CONTACT_EMAIL when that is set.
    SHOP_NAME                 name used in subjects and the signature, default "UA Market"

    MAIL_LOG_BODIES           write the text of an unsent message to the log. Default off.

Two states, and nothing in between:

* CONFIGURED — SMTP_HOST and MAIL_FROM are both set, and MAIL_FROM is a routable address
  (or SMTP_HOST is a local mail catcher such as `mailpit`). Messages go out over SMTP.
* DISABLED   — either is missing, or MAIL_FROM is a placeholder. Nothing is sent, nothing raises, and the log records who
  the message was for, what its subject was and how long it was. The text itself is written
  only when MAIL_LOG_BODIES is on, and a one-time locker code never survives that: it is
  cut out of the text before the line is written, and a body that still carries one is
  withheld whole. The password never reaches the log in either state.

`send_email` never raises. A refused connection, a bad login or a timeout comes back as
SendResult(sent=False, error=...) for the caller to record; an order is never held up by
the mail server.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from html import escape
from typing import Callable

from .routable import is_routable_email

log = logging.getLogger("uamarket.mail")

DEFAULT_SHOP_NAME = "UA Market"
DEFAULT_TIMEOUT_SECONDS = 15.0
SECURITY_CHOICES = {"starttls", "ssl", "none"}
# Hosts that only ever catch mail for a person to look at (Mailpit in docker compose).
LOCAL_CAPTURE_HOSTS = frozenset({"mailpit", "localhost", "127.0.0.1", "::1"})

# Tests and local runs replace this with a fake; production leaves it None and the
# SMTP transport below is used.
TRANSPORT: "Transport | None" = None


@dataclass(frozen=True)
class MailerConfig:
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""            # full From header value
    sender_email: str = ""      # bare address out of that header
    reply_to: str = ""
    security: str = "starttls"
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    shop_name: str = DEFAULT_SHOP_NAME

    @property
    def enabled(self) -> bool:
        if not (self.host and self.sender_email):
            return False
        # A placeholder sender (`shop@uamarket.local`) counts as unset, because a real
        # mailbox would reject or bin it. The one exception is a local mail catcher such
        # as Mailpit, which never delivers anywhere, so a local run can see its email.
        return is_routable_email(self.sender_email) or self.local_capture

    @property
    def local_capture(self) -> bool:
        return self.host.strip().lower() in LOCAL_CAPTURE_HOSTS

    def describe(self) -> dict:
        """Safe to log and to hand to an operator: no password, no login."""
        return {"host": self.host, "port": self.port, "security": self.security,
                "from": self.sender, "enabled": self.enabled}


@dataclass(frozen=True)
class SendResult:
    to: str
    subject: str
    sent: bool = False
    disabled: bool = False
    error: str | None = None
    message_id: str | None = None


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str
    # Values inside `text` that must never reach a log line — today, the one-time locker
    # code. The message still carries them to the customer; only the log is kept clean.
    secrets: tuple[str, ...] = ()


Transport = Callable[[MailerConfig, EmailMessage], None]


# --------------------------------------------------------------------------- config

def _clean(value: str | None) -> str:
    return (value or "").strip()


def _int(value: str | None, default: int) -> int:
    try:
        return int(_clean(value))
    except ValueError:
        return default


def _float(value: str | None, default: float) -> float:
    try:
        return float(_clean(value))
    except ValueError:
        return default


def load_config() -> MailerConfig:
    host = _clean(os.getenv("SMTP_HOST"))
    sender = _clean(os.getenv("MAIL_FROM"))
    sender_email = parseaddr(sender)[1] if sender else ""
    security = _clean(os.getenv("SMTP_SECURITY")).lower()
    port_raw = _clean(os.getenv("SMTP_PORT"))
    if security not in SECURITY_CHOICES:
        # An operator who points the shop at port 465 means the implicit-TLS port; every
        # other port defaults to STARTTLS, which is what "TLS on by default" means here.
        security = "ssl" if port_raw == "465" else "starttls"
    port = _int(port_raw, 465 if security == "ssl" else 587)
    reply_to = _clean(os.getenv("MAIL_REPLY_TO")) or _clean(os.getenv("SHOP_CONTACT_EMAIL"))
    return MailerConfig(
        host=host,
        port=port,
        username=_clean(os.getenv("SMTP_USER")),
        password=os.getenv("SMTP_PASSWORD") or "",
        sender=sender,
        sender_email=sender_email,
        reply_to=reply_to,
        security=security,
        timeout=_float(os.getenv("SMTP_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS),
        shop_name=_clean(os.getenv("SHOP_NAME")) or DEFAULT_SHOP_NAME,
    )


def email_enabled(config: MailerConfig | None = None) -> bool:
    return (config or load_config()).enabled


def sender_address(config: MailerConfig | None = None) -> str | None:
    """The address the customer will see mail arrive from, or None while disabled."""
    cfg = config or load_config()
    return cfg.sender_email if cfg.enabled else None


# --------------------------------------------------------------------------- message

def _header_safe(value: str) -> str:
    """One line only. A newline in a header is how header injection starts."""
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def build_message(cfg: MailerConfig, *, to: str, subject: str, text: str, html: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = _header_safe(cfg.sender)
    msg["To"] = _header_safe(to)
    msg["Subject"] = _header_safe(subject)
    msg["Date"] = formatdate(localtime=True)
    domain = cfg.sender_email.split("@")[-1] if "@" in cfg.sender_email else None
    msg["Message-ID"] = make_msgid(domain=domain) if domain else make_msgid()
    if cfg.reply_to:
        msg["Reply-To"] = _header_safe(cfg.reply_to)
    # RFC 3834: this is a machine-written message, so out-of-office replies stay away.
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


# --------------------------------------------------------------------------- transport

def _authenticate(cfg: MailerConfig, client: smtplib.SMTP) -> None:
    if cfg.username:
        client.login(cfg.username, cfg.password)


def smtp_transport(cfg: MailerConfig, msg: EmailMessage) -> None:
    """Deliver over SMTP. Raises on any SMTP or socket failure; `send_email` catches it."""
    if cfg.security == "ssl":
        with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=ssl.create_default_context()) as client:
            _authenticate(cfg, client)
            client.send_message(msg)
        return
    with smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout) as client:
        client.ehlo()
        if cfg.security == "starttls":
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        _authenticate(cfg, client)
        client.send_message(msg)


def _resolve_transport(transport: Transport | None) -> Transport:
    return transport or TRANSPORT or smtp_transport


# --------------------------------------------------------------------------- what may be logged
#
# A disabled mailer used to write the whole message to the log, which put the buyer's
# one-time locker code in plaintext in the application log — on the deployment where SMTP
# is off, which is the documented default. Two rules now:
#
#   * the log always names the recipient, the subject and the length of the body;
#   * the body itself is written only when MAIL_LOG_BODIES is on, with every code cut out
#     of it first, and a body that still carries one after that is withheld whole.

REDACTED = "[redacted]"


def log_bodies() -> bool:
    return (os.getenv("MAIL_LOG_BODIES") or "").strip().lower() in {"1", "true", "yes", "on"}


def _code_labels() -> tuple[str, ...]:
    """The line each language prints the one-time code on, straight out of the copy table."""
    return tuple(dict.fromkeys(table["pickup_code"] for table in _L.values()))


def _code_line_pattern() -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in _code_labels())
    return re.compile(rf"((?:{labels})\s*:\s*)(\S+)")


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """The message with every one-time code cut out of it.

    Two nets. The first is the exact values the caller handed over, which is how the code
    for this order is known. The second is the line the code is printed on, in either
    language, which catches a message built somewhere this function was not told about.
    """
    out = text
    for secret in secrets:
        secret = (secret or "").strip()
        if len(secret) >= 4:
            out = out.replace(secret, REDACTED)
    return _code_line_pattern().sub(rf"\1{REDACTED}", out)


def _loggable_body(text: str, secrets: tuple[str, ...]) -> str | None:
    """The text as it may be written to the log, or None when it may not be written."""
    if not log_bodies():
        return None
    body = redact(text, secrets)
    if any((s or "").strip() and (s or "").strip() in body for s in secrets):
        return None
    return body


# --------------------------------------------------------------------------- sending

def send_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    config: MailerConfig | None = None,
    transport: Transport | None = None,
    secrets: tuple[str, ...] = (),
) -> SendResult:
    """Send one message. Returns a result; raises nothing."""
    cfg = config or load_config()
    to = _header_safe(to)
    subject = _header_safe(subject)
    if not to or "@" not in to:
        log.warning("mail skipped, no usable recipient (subject=%r)", subject)
        return SendResult(to=to, subject=subject, error="no_recipient")
    if not cfg.enabled:
        log.info("mail DISABLED (SMTP_HOST/MAIL_FROM unset) — message not sent. "
                 "to=%s subject=%r body_length=%d", to, subject, len(text))
        body = _loggable_body(text, secrets)
        if body is not None:
            log.info("mail DISABLED body (MAIL_LOG_BODIES, one-time codes removed):\n%s", body)
        return SendResult(to=to, subject=subject, disabled=True)
    try:
        msg = build_message(cfg, to=to, subject=subject, text=text, html=html)
        _resolve_transport(transport)(cfg, msg)
    except Exception as exc:  # noqa: BLE001 - a mail server failure must not reach the caller
        log.warning("mail send failed to=%s subject=%r host=%s error=%s: %s",
                    to, subject, cfg.host, type(exc).__name__, exc)
        return SendResult(to=to, subject=subject, error=f"{type(exc).__name__}: {exc}")
    log.info("mail sent to=%s subject=%r", to, subject)
    return SendResult(to=to, subject=subject, sent=True, message_id=msg["Message-ID"])


def send_content(content: EmailContent, *, to: str, config: MailerConfig | None = None,
                 transport: Transport | None = None) -> SendResult:
    return send_email(to=to, subject=content.subject, text=content.text, html=content.html,
                      config=config, transport=transport, secrets=content.secrets)


# --------------------------------------------------------------------------- order mail

KINDS = ("placed", "paid", "pickup_ready", "handoff", "cancelled")

_L = {
    "en": {
        "subject_placed": "order {num} received",
        "subject_paid": "payment received for order {num}",
        "subject_pickup_ready": "order {num} is in the locker",
        "subject_handoff": "order {num} shipped",
        "subject_handoff_pickup": "order {num} collected",
        "subject_cancelled": "order {num} cancelled",
        "hello": "Hello {name},",
        "hello_plain": "Hello,",
        "intro_placed": "We have your order {num}.",
        "intro_paid": "Your payment for order {num} arrived. We are preparing the parcel.",
        "intro_pickup_ready": "Order {num} is in the locker and waiting for you.",
        "intro_handoff": "Order {num} is with the courier.",
        "intro_handoff_pickup": "Order {num} has left the locker.",
        "intro_cancelled": "Order {num} is cancelled and will not be sent.",
        "cancel_unpaid": "Nothing is owed on this order. Please do not send a payment for it.",
        "cancel_refund": "The payment for this order is being returned the way it was made. Write to us if it has not arrived.",
        "items": "Items",
        "subtotal": "Subtotal",
        "shipping": "Shipping",
        "tax": "Tax",
        "total": "Total",
        "delivery": "Delivery",
        "ship_to": "Shipping address:",
        "pickup": "Pickup",
        "pickup_address": "Address",
        "pickup_hours": "Hours",
        "pickup_bay": "Bay",
        "pickup_code": "One-time code",
        "pickup_valid": "The code opens the bay once, until {until}.",
        "pickup_collected": "The parcel has left the locker.",
        "payment": "Payment",
        "pay_etransfer": "Send {amount} by Interac e-Transfer to {email}. Put {num} in the message.",
        "pay_etransfer_after": "A person checks the transfer by hand. You get another email when it is confirmed.",
        "pay_stripe": "Pay by card here: {url}",
        "pay_stripe_nolink": "Open the order page to pay by card.",
        "pay_invoice": "We will write to you about payment{contact}.",
        "pay_invoice_contact": " from {email}",
        "paid_note": "Nothing is owed on this order.",
        "pay_demo": "This shop is showing demonstration goods, so this order is a test. Do not send money for it.",
        "pay_test": "Test payment page (no money moves): {url}",
        "tracking": "Tracking",
        "status": "Status",
        "order_page": "Order page: {url}",
        "order_page_plain": "Keep the order number {num}. The order page on the site shows the current status.",
        "questions": "Questions: {email}",
        "signature": "{shop}",
        "terms": "Terms of sale that apply to this order: {url}",
        "terms_version": "Terms of sale (version {version}) that apply to this order: {url}",
        "gst_number": "GST/HST registration: {number}",
        "open_order": "Open your order",
        "order_number": "Order",
        "qty": "Qty",
        "footer_auto": "The shop's system wrote this message when your order changed.",
    },
    "uk": {
        "subject_placed": "замовлення {num} отримано",
        "subject_paid": "оплату за замовлення {num} отримано",
        "subject_pickup_ready": "замовлення {num} у локері",
        "subject_handoff": "замовлення {num} відправлено",
        "subject_handoff_pickup": "замовлення {num} забрано",
        "subject_cancelled": "замовлення {num} скасовано",
        "hello": "Вітаємо, {name}!",
        "hello_plain": "Вітаємо!",
        "intro_placed": "Ваше замовлення {num} у нас.",
        "intro_paid": "Оплата за замовлення {num} надійшла. Готуємо посилку.",
        "intro_pickup_ready": "Замовлення {num} у локері та чекає на вас.",
        "intro_handoff": "Замовлення {num} у кур'єра.",
        "intro_handoff_pickup": "Замовлення {num} забрано з локера.",
        "intro_cancelled": "Замовлення {num} скасовано, посилку не надсилатимемо.",
        "cancel_unpaid": "За цим замовленням нічого сплачувати. Будь ласка, не надсилайте за нього гроші.",
        "cancel_refund": "Оплату за це замовлення повертаємо тим самим способом, яким її зроблено. Напишіть нам, якщо гроші не надійшли.",
        "items": "Товари",
        "subtotal": "Проміжна сума",
        "shipping": "Доставка",
        "tax": "Податок",
        "total": "Разом",
        "delivery": "Доставка",
        "ship_to": "Адреса доставки:",
        "pickup": "Самовивіз",
        "pickup_address": "Адреса",
        "pickup_hours": "Години",
        "pickup_bay": "Комірка",
        "pickup_code": "Одноразовий код",
        "pickup_valid": "Код відкриває комірку один раз, діє до {until}.",
        "pickup_collected": "Посилку забрано з локера.",
        "payment": "Оплата",
        "pay_etransfer": "Надішліть {amount} через Interac e-Transfer на {email}. У повідомленні вкажіть {num}.",
        "pay_etransfer_after": "Переказ звіряє людина. Щойно оплату підтверджено, ви отримаєте ще один лист.",
        "pay_stripe": "Оплатити карткою: {url}",
        "pay_stripe_nolink": "Відкрийте сторінку замовлення, щоб оплатити карткою.",
        "pay_invoice": "Ми напишемо вам щодо оплати{contact}.",
        "pay_invoice_contact": " з адреси {email}",
        "paid_note": "За цим замовленням більше нічого сплачувати.",
        "pay_demo": "Крамниця показує демонстраційні товари, тож це замовлення тестове. Не надсилайте за нього гроші.",
        "pay_test": "Тестова сторінка оплати (гроші не рухаються): {url}",
        "tracking": "Трекінг",
        "status": "Стан",
        "order_page": "Сторінка замовлення: {url}",
        "order_page_plain": "Збережіть номер замовлення {num}. Стан замовлення показує сторінка на сайті.",
        "questions": "Питання: {email}",
        "signature": "{shop}",
        "terms": "Умови продажу, що діють для цього замовлення: {url}",
        "terms_version": "Умови продажу (версія {version}), що діють для цього замовлення: {url}",
        "gst_number": "Реєстрація GST/HST: {number}",
        "open_order": "Відкрити замовлення",
        "order_number": "Замовлення",
        "qty": "К-сть",
        "footer_auto": "Цей лист надіслала система крамниці, коли змінився стан замовлення.",
    },
}


def _s(lang: str, key: str, **kw) -> str:
    table = _L.get(lang if lang in _L else "en", _L["en"])
    return table[key].format(**kw) if kw else table[key]


def money(value: float | int | None) -> str:
    return f"CA$ {float(value or 0):,.2f}"


def _line_label(line: dict, lang: str) -> str:
    title = line.get("title_uk") if lang == "uk" and line.get("title_uk") else line.get("title")
    label = (line.get("label_uk") if lang == "uk" and line.get("label_uk") else line.get("label"))
    return f"{title} ({label})" if label else str(title or "")


def _address_line(view: dict) -> str:
    ship = view.get("ship_to") or {}
    parts = [ship.get("name"), ship.get("street1"), ship.get("street2")]
    city = " ".join(p for p in [ship.get("city"), ship.get("province"), ship.get("postal_code")] if p)
    parts.append(city)
    return ", ".join(p for p in parts if p)


def _payment_lines(view: dict, lang: str, *, contact_email: str | None) -> list[str]:
    """The payment instruction that actually applies to this order, and no other."""
    payment = view.get("payment") or {}
    if not payment.get("due"):
        return [_s(lang, "paid_note")]
    if payment.get("demo"):
        rows = [_s(lang, "pay_demo")]
        if payment.get("method") == "STRIPE" and payment.get("checkout_url"):
            rows.append(_s(lang, "pay_test", url=payment["checkout_url"]))
        return rows
    amount = money(payment.get("amount_cad") if payment.get("amount_cad") is not None else (view.get("totals") or {}).get("total_cad"))
    method = payment.get("method")
    if method == "ETRANSFER" and payment.get("recipient_email"):
        return [
            _s(lang, "pay_etransfer", amount=amount, email=payment["recipient_email"],
               num=payment.get("message") or view.get("order_number") or ""),
            _s(lang, "pay_etransfer_after"),
        ]
    if method == "STRIPE":
        url = payment.get("checkout_url")
        return [_s(lang, "pay_stripe", url=url) if url else _s(lang, "pay_stripe_nolink")]
    email = payment.get("contact_email") or contact_email
    return [_s(lang, "pay_invoice", contact=_s(lang, "pay_invoice_contact", email=email) if email else "")]


def _pickup_block(view: dict, lang: str, *, kind: str, pickup_label: str | None) -> list[str]:
    """The delivery block of a pickup order.

    Every kind of message names the method. The "pickup_ready" message additionally carries
    what a person standing at the locker needs: the address, the hours when there are any,
    the bay, the code, and the hour the code stops working. It refuses to be built without
    the code and the address, because a message announcing a code and carrying none is the
    exact thing this email exists to stop.
    """
    pickup = view.get("pickup") or {}
    rows = [_s(lang, "delivery"), f"  {pickup_label or _s(lang, 'pickup')}"]
    if kind != "pickup_ready":
        if kind == "handoff":
            rows.append(f"  {_s(lang, 'pickup_collected')}")
        return rows
    code = pickup.get("code")
    address = pickup.get("address")
    if not code:
        raise ValueError("a pickup_ready email needs the one-time code on the order view")
    if not address:
        raise ValueError("a pickup_ready email needs the configured pickup address")
    rows.append(f"  {_s(lang, 'pickup_address')}: {address}")
    if pickup.get("hours"):
        rows.append(f"  {_s(lang, 'pickup_hours')}: {pickup['hours']}")
    if pickup.get("note"):
        rows.append(f"  {pickup['note']}")
    if pickup.get("bay"):
        rows.append(f"  {_s(lang, 'pickup_bay')}: {pickup['bay']}")
    rows.append(f"  {_s(lang, 'pickup_code')}: {code}")
    until = pickup.get("valid_until_text") or pickup.get("valid_until")
    if until:
        rows.append(f"  {_s(lang, 'pickup_valid', until=until)}")
    return rows


def render_order_email(
    view: dict,
    *,
    kind: str,
    lang: str = "en",
    shop_name: str = DEFAULT_SHOP_NAME,
    order_url: str | None = None,
    pickup_label: str | None = None,
    contact_email: str | None = None,
    terms_url: str | None = None,
    terms_version: str | None = None,
) -> EmailContent:
    """Build one order email out of the storefront's own order view.

    Every fact in the message is read from `view` (the payload the customer already sees
    on the order page): order number, lines with their variant labels, totals with the named
    tax lines, delivery method, payment instruction, tracking when a carrier has it. Nothing
    is added. The HTML part is the КАНВА layout (web/DESIGN.md): linen ground, a bleached
    receipt, mono money, one red button; it needs no images and reads the same with styles off.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown mail kind {kind!r}")
    lang = lang if lang in _L else "en"
    num = view.get("order_number") or ""
    name = ((view.get("customer") or {}).get("name") or "").strip()
    is_pickup = view.get("fulfillment_method") == "PICKUP"
    # A buyer who collects the parcel from the locker is never told it went to a courier.
    voice = f"{kind}_pickup" if (is_pickup and kind == "handoff") else kind
    subject = f"{shop_name} · {_s(lang, f'subject_{voice}', num=num)}"
    hello = _s(lang, "hello", name=name) if name else _s(lang, "hello_plain")
    intro = _s(lang, f"intro_{voice}", num=num)

    blocks: list[list[str]] = []
    blocks.append([hello, intro])

    lines = view.get("lines") or []
    if lines:
        rows = [f"  {l.get('qty')} × {_line_label(l, lang)} — {money(l.get('line_total_cad'))}" for l in lines]
        blocks.append([_s(lang, "items"), *rows])

    money_rows = _money_rows(view, lang)
    blocks.append([f"  {label}: {value}" for label, value, _ in money_rows])

    if is_pickup:
        delivery = _pickup_block(view, lang, kind=kind, pickup_label=pickup_label)
    else:
        address = _address_line(view)
        delivery = [_s(lang, "delivery"), f"  {_s(lang, 'ship_to')} {address}" if address else f"  {_s(lang, 'ship_to')}"]
    blocks.append(delivery)

    if kind == "cancelled":
        payment = [_s(lang, "cancel_refund" if view.get("paid_at") else "cancel_unpaid")]
    else:
        payment = _payment_lines(view, lang, contact_email=contact_email)
    blocks.append([_s(lang, "payment"), *[f"  {line}" for line in payment]])

    tracking = view.get("tracking") or {}
    tracking_text = None
    if tracking.get("code"):
        tracking_text = f"{tracking.get('carrier') or ''} {tracking['code']}".strip()
        blocks.append([_s(lang, "tracking"), f"  {tracking_text}"])

    status = view.get("status") or {}
    status_label = status.get("label_uk") if lang == "uk" and status.get("label_uk") else status.get("label")
    if status_label:
        blocks.append([f"{_s(lang, 'status')}: {status_label}"])

    blocks.append([_s(lang, "order_page", url=order_url) if order_url else _s(lang, "order_page_plain", num=num)])
    fine: list[str] = []
    if terms_url:
        fine.append(_s(lang, "terms_version", url=terms_url, version=terms_version) if terms_version else _s(lang, "terms", url=terms_url))
    if view.get("gst_number"):
        fine.append(_s(lang, "gst_number", number=view["gst_number"]))
    if contact_email:
        fine.append(_s(lang, "questions", email=contact_email))
    for line in fine:
        blocks.append([line])
    blocks.append([_s(lang, "signature", shop=shop_name)])

    text = "\n\n".join("\n".join(block) for block in blocks) + "\n"
    code = str(((view.get("pickup") or {}).get("code") or "")).strip()
    html = _html_email(
        lang=lang, shop_name=shop_name, subject=subject, num=num, hello=hello, intro=intro,
        lines=lines, money_rows=money_rows, delivery=delivery, payment=payment, tracking=tracking_text,
        status=status_label, order_url=order_url, fine=fine, terms_url=terms_url,
    )
    return EmailContent(subject=subject, text=text, html=html, secrets=(code,) if code else ())


def _money_rows(view: dict, lang: str) -> list[tuple[str, str, bool]]:
    """(label, amount, is_total) for subtotal, shipping, each named tax line and the total."""
    totals = view.get("totals") or {}
    rows = [(_s(lang, "subtotal"), money(totals.get("subtotal_cad")), False)]
    if totals.get("shipping_cad"):
        rows.append((_s(lang, "shipping"), money(totals.get("shipping_cad")), False))
    tax_lines = totals.get("tax_lines") or []
    if tax_lines:
        for line in tax_lines:
            label = line.get("label_uk") if lang == "uk" and line.get("label_uk") else line.get("label")
            rows.append((str(label or _s(lang, "tax")), money(line.get("amount_cad")), False))
    elif totals.get("tax_cad"):
        rate = totals.get("tax_rate")
        label = f"{_s(lang, 'tax')} ({round(float(rate) * 100)}%)" if rate else _s(lang, "tax")
        rows.append((label, money(totals.get("tax_cad")), False))
    rows.append((_s(lang, "total"), money(totals.get("total_cad")), True))
    return rows


# КАНВА tokens for mail clients, which ignore CSS variables: web/app/globals.css :root.
_C = {
    "linen": "#D9D2C1", "bleached": "#E8E3D6", "shade": "#CBC3B0", "ink": "#221E1B", "plate": "#1E1A17",
    "red": "#A11D2B", "white": "#EFE9DC", "muted": "#574F48", "mustard": "#715608",
}
_TEXT = "font-family:'Fixel Text',Helvetica,Arial,sans-serif;"
_MONO = "font-family:'Fira Mono',Menlo,Consolas,monospace;"


def _linkify(value: str, url: str | None) -> str:
    """Escape a line; only the shop's own link passed in `url` (order page, terms) becomes a link."""
    safe = escape(value)
    if url and escape(url) in safe:
        href = escape(url, quote=True)
        safe = safe.replace(escape(url), f'<a href="{href}" style="color:{_C["red"]};">{href}</a>')
    return safe


def _html_email(*, lang: str, shop_name: str, subject: str, num: str, hello: str, intro: str, lines: list[dict],
                money_rows: list[tuple[str, str, bool]], delivery: list[str], payment: list[str],
                tracking: str | None, status: str | None, order_url: str | None, fine: list[str],
                terms_url: str | None) -> str:
    c = _C
    head_cell = f'style="{_MONO}font-size:12px;line-height:24px;color:{c["muted"]};padding:0 0 4px 0;"'

    def section(title: str, body_rows: list[str]) -> str:
        body = "".join(
            f'<div style="{_TEXT}font-size:15px;line-height:24px;color:{c["ink"]};">{_linkify(r.strip(), order_url)}</div>'
            for r in body_rows if r.strip()
        )
        return (f'<tr><td style="padding:16px 24px 0 24px;"><div {head_cell}>{escape(title)}</div>{body}</td></tr>')

    item_rows = "".join(
        '<tr>'
        f'<td style="{_MONO}font-size:13px;line-height:24px;color:{c["muted"]};padding:6px 12px 6px 0;vertical-align:top;white-space:nowrap;">{int(l.get("qty") or 0)} ×</td>'
        f'<td style="{_TEXT}font-size:15px;line-height:24px;color:{c["ink"]};padding:6px 12px 6px 0;vertical-align:top;">{escape(_line_label(l, lang))}</td>'
        f'<td align="right" style="{_MONO}font-size:14px;line-height:24px;color:{c["ink"]};padding:6px 0;vertical-align:top;white-space:nowrap;">{escape(money(l.get("line_total_cad")))}</td>'
        '</tr>'
        for l in lines
    )
    total_rows = "".join(
        '<tr>'
        f'<td colspan="2" style="{_MONO}font-size:{14 if total else 13}px;line-height:24px;color:{c["ink"] if total else c["muted"]};padding:{"10px" if total else "2px"} 12px 2px 0;{"border-top:1px dashed " + c["ink"] + ";font-weight:bold;" if total else ""}">{escape(label)}</td>'
        f'<td align="right" style="{_MONO}font-size:{15 if total else 14}px;line-height:24px;color:{c["ink"]};padding:{"10px" if total else "2px"} 0 2px 0;white-space:nowrap;{"border-top:1px dashed " + c["ink"] + ";font-weight:bold;" if total else ""}">{escape(value)}</td>'
        '</tr>'
        for label, value, total in money_rows
    )
    button = ""
    if order_url:
        href = escape(order_url, quote=True)
        button = (
            '<tr><td style="padding:24px 24px 0 24px;">'
            f'<a href="{href}" style="display:inline-block;background:{c["red"]};color:{c["white"]};{_TEXT}font-size:15px;'
            f'font-weight:bold;line-height:24px;padding:12px 24px;text-decoration:none;">{escape(_s(lang, "open_order"))} →</a>'
            '</td></tr>'
        )
    tracking_html = section(_s(lang, "tracking"), [tracking]) if tracking else ""
    status_html = (
        f'<tr><td style="padding:16px 24px 0 24px;"><span style="{_MONO}font-size:12px;line-height:24px;color:{c["muted"]};">'
        f'{escape(_s(lang, "status"))}: </span><span style="{_MONO}font-size:13px;line-height:24px;color:{c["ink"]};">{escape(status)}</span></td></tr>'
        if status else ""
    )
    fine_html = "".join(
        f'<div style="{_MONO}font-size:12px;line-height:20px;color:{c["muted"]};padding-top:4px;">{_linkify(f, terms_url)}</div>'
        for f in fine
    )
    return f"""<!doctype html>
<html lang="{'uk' if lang == 'uk' else 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{c['linen']};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{c['linen']};">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;">
<tr><td style="padding:0 0 12px 0;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="font-family:Helvetica,Arial,sans-serif;font-size:22px;line-height:24px;font-weight:bold;color:{c['red']};padding-right:10px;">✕</td>
<td style="font-family:'Fixel Display',Helvetica,Arial,sans-serif;font-size:22px;line-height:24px;font-weight:900;letter-spacing:-0.02em;color:{c['ink']};">{escape(shop_name)}</td>
</tr></table></td></tr>
<tr><td style="background:{c['bleached']};border-top:3px solid {c['red']};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="padding:24px 24px 0 24px;">
<div style="{_MONO}font-size:12px;line-height:24px;color:{c['muted']};">{escape(_s(lang, 'order_number'))} {escape(num)}</div>
<div style="font-family:'Fixel Display',Helvetica,Arial,sans-serif;font-size:26px;line-height:32px;font-weight:bold;color:{c['ink']};padding-top:4px;">{escape(intro)}</div>
<div style="{_TEXT}font-size:15px;line-height:24px;color:{c['ink']};padding-top:12px;">{escape(hello)}</div>
</td></tr>
<tr><td style="padding:16px 24px 0 24px;">
<div {head_cell}>{escape(_s(lang, 'items'))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px dashed {c['shade']};">
{item_rows}
<tr><td colspan="3" style="height:8px;border-bottom:1px dashed {c['shade']};font-size:0;line-height:0;">&nbsp;</td></tr>
{total_rows}
</table></td></tr>
{section(delivery[0], delivery[1:])}
{section(_s(lang, 'payment'), payment)}
{tracking_html}
{status_html}
{button}
<tr><td style="padding:24px 24px 24px 24px;">
<div style="border-top:1px dashed {c['shade']};padding-top:12px;">{fine_html}</div>
</td></tr>
</table></td></tr>
<tr><td style="padding:12px 0 0 0;{_MONO}font-size:11px;line-height:18px;color:{c['muted']};">{escape(_s(lang, 'footer_auto'))}<br>{escape(shop_name)}</td></tr>
</table></td></tr></table>
</body></html>"""
