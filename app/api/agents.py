"""The two agents' HTTP doors: the shopping concierge (public) and the PayPal desk (owner)."""
from __future__ import annotations

import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_operator
from ..deps import get_db
from ..services import concierge, desk, llm, paypal
from ..services.ratelimit import RateLimiter, client_address

router = APIRouter()

# Per visitor: a conversation is a handful of turns. Across everyone: a daily ceiling, so a
# public demo cannot run up the model bill.
agent_limiter = RateLimiter(limit=int(os.getenv("AGENT_TURNS_PER_10MIN") or 30), window_seconds=600)
_day = {"date": None, "count": 0}
_day_lock = threading.Lock()


def _daily_allow() -> bool:
    cap = int(os.getenv("AGENT_DAILY_TURNS") or 1500)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with _day_lock:
        if _day["date"] != today:
            _day.update(date=today, count=0)
        if _day["count"] >= cap:
            return False
        _day["count"] += 1
        return True


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class KnownOrder(BaseModel):
    order_number: str = Field(max_length=32)
    token: str = Field(max_length=64)


class BagLine(BaseModel):
    sku: str = Field(max_length=90)
    qty: int = Field(ge=1, le=5)


class ShopChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)
    locale: str = "en"
    budget_cad: float | None = Field(default=None, ge=0, le=100000)
    orders: list[KnownOrder] = Field(default_factory=list, max_length=10)
    bag: list[BagLine] = Field(default_factory=list, max_length=8)


class DeskChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)


@router.get("/v1/agent/status")
def agent_status():
    return {"concierge": llm.configured(), "model": llm.model() if llm.configured() else None,
            "paypal": paypal.public_config() is not None, "paypal_env": paypal.environment()}


@router.post("/v1/agent/shop")
def shop_chat(inp: ShopChatIn, request: Request, db: Session = Depends(get_db)):
    if not llm.configured():
        raise HTTPException(503, {"code": "agent_off", "message": "The shopping assistant is switched off on this shop"})
    if not agent_limiter.allow(client_address(request)) or not _daily_allow():
        raise HTTPException(429, {"code": "rate_limited", "message": "The assistant needs a short break; try again in a few minutes"})
    try:
        return concierge.chat(db, messages=[m.model_dump() for m in inp.messages], locale=inp.locale,
                              budget_cad=inp.budget_cad, orders=[o.model_dump() for o in inp.orders],
                              bag=[b.model_dump() for b in inp.bag])
    except ValueError as exc:
        raise HTTPException(400, {"code": "messages", "message": str(exc)})
    except llm.LLMError as exc:
        raise HTTPException(502, {"code": "model", "message": str(exc)})
    finally:
        db.rollback()  # the concierge only reads; nothing it touched is kept


@router.post("/v1/admin/agent/desk", dependencies=[Depends(require_operator)])
def desk_chat(inp: DeskChatIn, db: Session = Depends(get_db)):
    if not llm.configured():
        raise HTTPException(503, {"code": "agent_off", "message": "No language model is configured"})
    try:
        return desk.chat(db, messages=[m.model_dump() for m in inp.messages])
    except ValueError as exc:
        raise HTTPException(400, {"code": "messages", "message": str(exc)})
    except llm.LLMError as exc:
        raise HTTPException(502, {"code": "model", "message": str(exc)})
    finally:
        db.rollback()  # proposals only; a confirmed action goes through its own endpoint
