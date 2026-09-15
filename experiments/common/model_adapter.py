"""Local model adapter for Ollama, with the two candidate decision interfaces.

Both interfaces are held to identical conditions: same model, same context
string, same policy text, same inference options, same hardware. The only thing
that varies is *how the model is asked to emit the decision*, and both are
mapped onto the same canonical `Decision` before scoring.

Interface A — STRICT_JSON
    Ollama structured outputs: a JSON Schema is passed as `format`, so the
    runtime constrains generation to schema-valid JSON.

Interface B — NATIVE_TOOLS
    Ollama/Qwen native tool calling: each decision kind is a tool, and the
    model answers by calling exactly one of them.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from .contracts import Decision, ALLOWED_ACTIONS, ALLOWED_KINDS

DEFAULT_HOST = "http://127.0.0.1:11434"

STRICT_JSON = "STRICT_JSON"
NATIVE_TOOLS = "NATIVE_TOOLS"


# --------------------------------------------------------------------------
# Shared decision vocabulary (identical semantics for both interfaces)
# --------------------------------------------------------------------------

DECISION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": sorted(ALLOWED_KINDS)},
        "action": {"type": "string", "enum": sorted(ALLOWED_ACTIONS) + [""]},
        "target": {"type": "string"},
        "text": {"type": "string"},
        "option": {"type": "string"},
        "key": {"type": "string"},
        "url": {"type": "string"},
        "page_id": {"type": "string"},
        "reason_short": {"type": "string"},
    },
    "required": ["kind", "reason_short"],
}

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "browser_action",
            "description": (
                "Perform exactly one browser action against a target taken verbatim "
                "from the CURRENT OBSERVATION."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": sorted(ALLOWED_ACTIONS),
                        "description": "The browser action to perform.",
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "Target id copied exactly from the current observation, "
                            "e.g. obs_00012:f0:e7. Required for CLICK, TYPE, SELECT, PRESS."
                        ),
                    },
                    "text": {"type": "string", "description": "Text for TYPE."},
                    "option": {"type": "string", "description": "Option value for SELECT."},
                    "key": {"type": "string", "description": "Key name for PRESS."},
                    "url": {"type": "string", "description": "URL for NAVIGATE or NEW_TAB."},
                    "page_id": {"type": "string", "description": "Page id for SWITCH_TAB."},
                    "reason_short": {"type": "string"},
                },
                "required": ["action", "reason_short"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract",
            "description": "Record a fact that is visible in the current observation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The value being recorded."},
                    "target": {"type": "string"},
                    "reason_short": {"type": "string"},
                },
                "required": ["reason_short"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Hand control to the human. Use for passwords, two-factor codes, "
                "CAPTCHA, account choices and anything only the person can decide."
            ),
            "parameters": {
                "type": "object",
                "properties": {"reason_short": {"type": "string"}},
                "required": ["reason_short"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_confirmation",
            "description": (
                "Ask the user to approve a consequential, hard-to-undo action "
                "before it is performed."
            ),
            "parameters": {
                "type": "object",
                "properties": {"reason_short": {"type": "string"}},
                "required": ["reason_short"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replan",
            "description": "No allowed action on this page advances the current subgoal.",
            "parameters": {
                "type": "object",
                "properties": {"reason_short": {"type": "string"}},
                "required": ["reason_short"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Every success criterion is already satisfied.",
            "parameters": {
                "type": "object",
                "properties": {"reason_short": {"type": "string"}},
                "required": ["reason_short"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fail",
            "description": "The goal cannot be achieved and no replan would help.",
            "parameters": {
                "type": "object",
                "properties": {"reason_short": {"type": "string"}},
                "required": ["reason_short"],
            },
        },
    },
]

TOOL_TO_KIND = {
    "browser_action": "BROWSER_ACTION",
    "extract": "EXTRACT",
    "ask_user": "ASK_USER",
    "request_confirmation": "REQUEST_CONFIRMATION",
    "replan": "REPLAN",
    "finish": "FINISH",
    "fail": "FAIL",
}


@dataclass
class ModelCall:
    """Raw evidence for one model invocation. Always preserved."""

    interface: str
    ok: bool
    decision: Optional[Decision]
    raw_response: Any
    error: Optional[str]
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    n_tool_calls: int = 0

    def to_json(self) -> dict:
        return {
            "interface": self.interface,
            "ok": self.ok,
            "decision": self.decision.to_json() if self.decision else None,
            "raw_response": self.raw_response,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 1),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "n_tool_calls": self.n_tool_calls,
        }


class OllamaAdapter:
    def __init__(
        self,
        model: str = "qwen3:8b",
        host: str = DEFAULT_HOST,
        temperature: float = 0.0,
        seed: int = 7,
        num_ctx: int = 8192,
        num_predict: int = 300,
        think: bool = False,
        timeout: float = 300.0,
    ):
        self.model = model
        self.host = host
        self.options = {
            "temperature": temperature,
            "seed": seed,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "top_p": 1.0,
            "top_k": 0,
        }
        self.think = think
        self.timeout = timeout

    # ---------------------------------------------------------------- http

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            self.host + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def warmup(self):
        self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "ok"}],
                "stream": False,
                "think": self.think,
                "options": {**self.options, "num_predict": 1},
            },
        )

    # ------------------------------------------------------------- decide

    def decide(self, interface: str, system: str, user: str) -> ModelCall:
        if interface == STRICT_JSON:
            return self._decide_json(system, user)
        if interface == NATIVE_TOOLS:
            return self._decide_tools(system, user)
        raise ValueError(interface)

    def _base(self, system, user) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": self.think,
            "options": self.options,
        }

    def _decide_json(self, system, user) -> ModelCall:
        body = self._base(system, user)
        body["format"] = DECISION_JSON_SCHEMA
        t0 = time.perf_counter()
        try:
            res = self._post("/api/chat", body)
        except Exception as e:
            return ModelCall(
                STRICT_JSON, False, None, {"exception": str(e)[:500]},
                f"transport: {type(e).__name__}: {e}",
                (time.perf_counter() - t0) * 1000, 0, 0,
            )
        dt = (time.perf_counter() - t0) * 1000
        content = (res.get("message") or {}).get("content", "")
        try:
            obj = json.loads(content)
        except Exception as e:
            return ModelCall(
                STRICT_JSON, False, None, content, f"json_parse: {e}", dt,
                res.get("prompt_eval_count", 0), res.get("eval_count", 0),
            )
        dec, err = normalize_json_decision(obj)
        return ModelCall(
            STRICT_JSON, dec is not None, dec, obj, err, dt,
            res.get("prompt_eval_count", 0), res.get("eval_count", 0),
        )

    def _decide_tools(self, system, user) -> ModelCall:
        body = self._base(system, user)
        body["tools"] = TOOL_DEFS
        t0 = time.perf_counter()
        try:
            res = self._post("/api/chat", body)
        except Exception as e:
            return ModelCall(
                NATIVE_TOOLS, False, None, {"exception": str(e)[:500]},
                f"transport: {type(e).__name__}: {e}",
                (time.perf_counter() - t0) * 1000, 0, 0,
            )
        dt = (time.perf_counter() - t0) * 1000
        msg = res.get("message") or {}
        calls = msg.get("tool_calls") or []
        raw = {"tool_calls": calls, "content": msg.get("content", "")}
        pt, ct = res.get("prompt_eval_count", 0), res.get("eval_count", 0)
        if not calls:
            return ModelCall(
                NATIVE_TOOLS, False, None, raw,
                "no_tool_call: model answered in prose instead of calling a tool",
                dt, pt, ct, 0,
            )
        dec, err = normalize_tool_decision(calls[0])
        return ModelCall(
            NATIVE_TOOLS, dec is not None, dec, raw, err, dt, pt, ct, len(calls)
        )


# --------------------------------------------------------------------------
# Normalisation: both interfaces collapse onto the same canonical Decision
# --------------------------------------------------------------------------


def _args_from(kind: str, action: Optional[str], src: dict) -> dict:
    args: dict[str, Any] = {}
    if kind != "BROWSER_ACTION":
        return args
    if action == "TYPE" and src.get("text"):
        args["text"] = src["text"]
    if action == "SELECT" and (src.get("option") or src.get("text")):
        args["option"] = src.get("option") or src.get("text")
    if action == "PRESS" and src.get("key"):
        args["key"] = src["key"]
    if action in ("NAVIGATE", "NEW_TAB") and src.get("url"):
        args["url"] = src["url"]
    if action == "SWITCH_TAB" and src.get("page_id"):
        args["page_id"] = src["page_id"]
    return args


def normalize_json_decision(obj: Any) -> tuple[Optional[Decision], Optional[str]]:
    if not isinstance(obj, dict):
        return None, "not_an_object"
    kind = str(obj.get("kind") or "").strip().upper()
    if kind not in ALLOWED_KINDS:
        return None, f"invalid_kind: {kind!r}"
    action = (str(obj.get("action") or "").strip().upper()) or None
    if kind == "BROWSER_ACTION":
        if action not in ALLOWED_ACTIONS:
            return None, f"invalid_action: {action!r}"
    else:
        action = None
    target = (str(obj.get("target") or "").strip()) or None
    return (
        Decision(
            kind=kind,
            action=action,
            target=target,
            args=_args_from(kind, action, obj),
            reason_short=str(obj.get("reason_short") or "")[:200],
        ),
        None,
    )


def normalize_tool_decision(call: dict) -> tuple[Optional[Decision], Optional[str]]:
    fn = (call or {}).get("function") or {}
    name = fn.get("name") or ""
    kind = TOOL_TO_KIND.get(name)
    if kind is None:
        return None, f"unknown_tool: {name!r}"
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return None, "tool_arguments_not_json"
    if not isinstance(args, dict):
        args = {}
    action = (str(args.get("action") or "").strip().upper()) or None
    if kind == "BROWSER_ACTION":
        if action not in ALLOWED_ACTIONS:
            return None, f"invalid_action: {action!r}"
    else:
        action = None
    target = (str(args.get("target") or "").strip()) or None
    return (
        Decision(
            kind=kind,
            action=action,
            target=target,
            args=_args_from(kind, action, args),
            reason_short=str(args.get("reason_short") or "")[:200],
        ),
        None,
    )
