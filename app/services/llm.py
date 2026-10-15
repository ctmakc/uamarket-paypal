"""One OpenAI-compatible chat-completions client with a tool loop, for both shop agents.

The provider is configuration: AI_BASE_URL (default Ollama Cloud, https://ollama.com/v1),
AI_API_KEY, AI_MODEL (default gpt-oss:120b). Any server that speaks /chat/completions with
`tools` works: a local Ollama, vLLM, OpenAI, Gemini's OpenAI endpoint.

The model never touches money or the database directly. It asks for tools by name; the
caller's Python functions run them with their own validation and return JSON the model reads.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

log = logging.getLogger("uamarket.llm")

# Tests swap this for an httpx.MockTransport.
TRANSPORT: httpx.BaseTransport | None = None


def base_url() -> str:
    return (os.getenv("AI_BASE_URL") or "https://ollama.com/v1").strip().rstrip("/")


def model() -> str:
    return (os.getenv("AI_MODEL") or "gpt-oss:120b").strip()


def api_key() -> str:
    return (os.getenv("AI_API_KEY") or "").strip()


def configured() -> bool:
    # A local server (Ollama on localhost) needs no key; a remote one does.
    url = base_url()
    return bool(api_key()) or url.startswith("http://127.0.0.1") or url.startswith("http://localhost") \
        or url.startswith("http://ollama") or url.startswith("http://host.docker.internal")


class LLMError(RuntimeError):
    pass


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict], dict]

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.parameters}}


@dataclass
class Turn:
    reply: str
    trace: list[dict] = field(default_factory=list)
    rounds: int = 0


def _complete(messages: list[dict], tools: list[Tool], *, temperature: float) -> dict:
    body = {"model": model(), "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = [t.schema() for t in tools]
    headers = {"Content-Type": "application/json"}
    if api_key():
        headers["Authorization"] = f"Bearer {api_key()}"
    last = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=90, transport=TRANSPORT) as http:
                resp = http.post(f"{base_url()}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            last = f"{exc.__class__.__name__}"
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code in {429, 500, 502, 503, 504}:
            last = f"HTTP {resp.status_code}"
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code >= 300:
            raise LLMError(f"The language model refused the request (HTTP {resp.status_code})")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("The language model returned no answer")
        return choices[0].get("message") or {}
    raise LLMError(f"The language model could not be reached ({last})")


def run(system: str, history: list[dict], tools: list[Tool], *, max_rounds: int = 6, temperature: float = 0.2) -> Turn:
    """Ask the model, run the tools it calls, feed the results back, until it answers in text."""
    if not configured():
        raise LLMError("No language model is configured (AI_BASE_URL / AI_API_KEY)")
    by_name = {t.name: t for t in tools}
    messages = [{"role": "system", "content": system}, *history]
    trace: list[dict] = []
    for round_no in range(1, max_rounds + 1):
        msg = _complete(messages, tools, temperature=temperature)
        calls = msg.get("tool_calls") or []
        if not calls:
            return Turn(reply=(msg.get("content") or "").strip(), trace=trace, rounds=round_no)
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            fn = (call.get("function") or {})
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments must be an object")
            except ValueError:
                args = {}
                result = {"error": "Arguments were not valid JSON; call the tool again with a JSON object."}
            else:
                tool = by_name.get(name)
                if tool is None:
                    result = {"error": f"There is no tool named {name}."}
                else:
                    try:
                        result = tool.run(args)
                    except Exception as exc:  # a tool failure is information for the model, not a crash
                        log.exception("tool %s failed", name)
                        result = {"error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}
            trace.append({"tool": name, "args": args, "ok": "error" not in result})
            messages.append({"role": "tool", "tool_call_id": call.get("id") or name, "name": name,
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:12000]})
    # Out of rounds: ask once more without tools so the buyer still gets a sentence.
    msg = _complete(messages + [{"role": "user", "content": "(Answer now in one short paragraph with what you have.)"}], [],
                    temperature=temperature)
    return Turn(reply=(msg.get("content") or "").strip(), trace=trace, rounds=max_rounds + 1)
