"""Canadian sales tax on a web order, as named lines.

    SHOP_TAX_MODE                 unregistered | gst_hst_registered | custom
    SHOP_PST_REGISTERED_PROVINCES provinces where the shop is registered for the provincial
                                  tax too (BC, MB, SK, QC), comma-separated. Empty = none.
    SHOP_GST_NUMBER               the GST/HST registration number printed on the order page
                                  and in the order email. Empty = nothing printed.
    TAX_RATES_JSON                custom mode only: {"ON": 0.13, ...}, one "Sales tax" line.

While SHOP_TAX_MODE is empty the shop reads TAX_RATES_JSON when it is set (custom) and adds
no tax otherwise (unregistered). A small supplier that is not registered for GST/HST does
not charge it, so "no line" is the honest default.

The place of supply is the province the parcel is delivered to, or the pickup province for
a locker order. The tax is computed on goods plus shipping.

Rates below were fetched and compared on 2026-09-17 (all matched; quotes in
docs/DECISIONS-2026-09-17.md) against the Canada Revenue Agency GST/HST rate table
https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate/calculator.html
(Nova Scotia's HST is 14% since 2025-04-01), Revenu Québec for QST
https://www.revenuquebec.ca/en/businesses/consumption-taxes/gsthst-and-qst/collecting-gst-and-qst/calculating-the-taxes/,
British Columbia PST https://www2.gov.bc.ca/gov/content/taxes/sales-taxes/pst,
Manitoba RST https://www.gov.mb.ca/finance/taxation/taxes/retail.html and
Saskatchewan PST https://www.saskatchewan.ca/business/taxes-licensing-and-reporting/provincial-taxes-policies-and-bulletins/provincial-sales-tax.
They need the shop's accountant to confirm them before the first taxed order (see
docs/OWNER-ACTIONS.md), including whether shipping charges carry the provincial tax.
"""
from __future__ import annotations

import json
import os

MODES = ("unregistered", "gst_hst_registered", "custom")

GST = 0.05

# Federal component per province: GST (5%) or the harmonized HST.
FEDERAL: dict[str, tuple[str, float]] = {
    "AB": ("GST", GST), "BC": ("GST", GST), "MB": ("GST", GST), "NT": ("GST", GST), "NU": ("GST", GST),
    "QC": ("GST", GST), "SK": ("GST", GST), "YT": ("GST", GST),
    "ON": ("HST", 0.13), "NB": ("HST", 0.15), "NL": ("HST", 0.15), "PE": ("HST", 0.15), "NS": ("HST", 0.14),
}

# Provincial component, charged only where the shop has registered for it.
PROVINCIAL: dict[str, tuple[str, float]] = {
    "QC": ("QST", 0.09975),
    "BC": ("PST", 0.07),
    "MB": ("RST", 0.07),
    "SK": ("PST", 0.06),
}

LABELS_UK = {"GST": "GST", "HST": "HST", "QST": "QST", "PST": "PST", "RST": "RST", "TAX": "Податок з продажу"}
LABELS_EN = {"GST": "GST", "HST": "HST", "QST": "QST", "PST": "PST", "RST": "RST", "TAX": "Sales tax"}


def _rates_json() -> dict[str, float]:
    raw = os.getenv("TAX_RATES_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    out = {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        try:
            out[str(k).upper()] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def tax_mode() -> str:
    raw = (os.getenv("SHOP_TAX_MODE") or "").strip().lower()
    if raw in MODES:
        return raw
    return "custom" if _rates_json() else "unregistered"


def pst_registered() -> set[str]:
    return {p.strip().upper() for p in (os.getenv("SHOP_PST_REGISTERED_PROVINCES") or "").split(",") if p.strip()}


def gst_number() -> str | None:
    value = (os.getenv("SHOP_GST_NUMBER") or "").strip()
    return value[:40] or None


def components(province: str | None) -> list[dict]:
    """The tax components that apply to a sale delivered in `province`, as {code, rate}."""
    prov = (province or "").strip().upper()
    mode = tax_mode()
    if mode == "unregistered" or not prov:
        return []
    if mode == "custom":
        rate = _rates_json().get(prov)
        return [{"code": "TAX", "rate": rate}] if rate else []
    out = []
    federal = FEDERAL.get(prov)
    if federal:
        out.append({"code": federal[0], "rate": federal[1]})
    provincial = PROVINCIAL.get(prov)
    if provincial and prov in pst_registered():
        out.append({"code": provincial[0], "rate": provincial[1]})
    return out


def tax_lines(taxable: float, province: str | None) -> list[dict]:
    """Named lines for this taxable amount: code, EN/UK label, rate, amount (rounded per line)."""
    lines = []
    for c in components(province):
        amount = round(taxable * c["rate"] + 1e-9, 2)
        pct = round(c["rate"] * 100, 3)
        pct_text = f"{pct:g}%"
        lines.append({
            "code": c["code"],
            "label": f"{LABELS_EN[c['code']]} ({pct_text})",
            "label_uk": f"{LABELS_UK[c['code']]} ({pct_text})",
            "rate": c["rate"],
            "amount_cad": amount,
        })
    return lines


def configured_provinces() -> list[str]:
    """Provinces where a tax line appears at checkout."""
    from .storefront import PROVINCES

    return sorted(p for p in PROVINCES if components(p))


def config() -> dict:
    return {
        "mode": tax_mode(),
        "configured_provinces": configured_provinces(),
        "gst_number": gst_number(),
    }
