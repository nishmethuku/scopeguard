"""Drop-in ToolsExecutor for AgentDojo that applies ScopeGuard's provenance and reversibility rules.

AgentDojo tools carry no effect metadata, so effects are inferred from the tool name and arguments. This is a
deliberately simple, transparent version of Layer 2 (no model call): it is meant for the "unmodified AgentDojo"
generalization check (E5), where the guard must work on a benchmark it was not written for.

Rule: before a side-effecting call runs, every recipient-like argument (email, URL, IBAN, phone, or an argument
named to/recipient/...) must appear in the user's own request. A value that appears only in tool output was
supplied by third-party content and the call is blocked (irreversible) or treated as an unanswered ask (reversible).
Read-only calls always run.

    from agentdojo.agent_pipeline import AgentPipeline, ToolsExecutionLoop
    from scopeguard.integrations.agentdojo_guard import GuardedToolsExecutor
    pipeline = AgentPipeline([system, init_query, llm, ToolsExecutionLoop([GuardedToolsExecutor(), llm])])

Status: unit-tested against AgentDojo's runtime types. A full benchmark run needs a model API key and has not been
done; report utility (benign task success) alongside attack success, since this rule can block legitimate calls.
"""
from __future__ import annotations

import re
from typing import Any

from agentdojo.agent_pipeline import ToolsExecutor
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.types import ChatToolResultMessage, text_content_block_from_string

READ_VERBS = ("get", "read", "search", "list", "check", "find", "view", "show", "download", "fetch", "look", "query", "count", "calculate")
IRREVERSIBLE = ("send", "pay", "transfer", "delete", "remove", "share", "post", "cancel", "reset", "wire", "forward", "publish")
RECIPIENT_ARGS = {"to", "recipient", "recipients", "email", "emails", "iban", "url", "participants", "phone", "attendees", "cc", "bcc", "address"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"https?://[^\s'\"]+|www\.[^\s'\"]+")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")


def classify(tool_name: str) -> str:
    n = tool_name.lower()
    if any(n.startswith(v) or f"_{v}" in n for v in IRREVERSIBLE):
        return "irreversible"
    if any(n.startswith(v) or f"_{v}_" in n for v in READ_VERBS):
        return "read"
    return "reversible"


def _strings(v: Any):
    if isinstance(v, str):
        yield v
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)


def recipient_values(args: dict) -> list[str]:
    out = []
    for k, v in args.items():
        for s in _strings(v):
            if k.lower() in RECIPIENT_ARGS or EMAIL.fullmatch(s.strip()) or URL.fullmatch(s.strip()) or IBAN.fullmatch(s.strip()):
                out.append(s.strip())
    return out


def user_request_text(query: str, messages) -> str:
    parts = [query or ""]
    for m in messages:
        if m.get("role") == "user":
            parts += [b.get("content", "") for b in (m.get("content") or []) if isinstance(b, dict)]
    return "\n".join(parts).lower()


def judge(tool_name: str, args: dict, user_text: str) -> tuple[str, str]:
    kind = classify(tool_name)
    if kind == "read":
        return "allow", ""
    for val in recipient_values(args):
        if val.lower() not in user_text:
            if kind == "irreversible":
                return "block", f"'{val}' in {tool_name} came from tool output, not from the user's request"
            return "block", f"'{val}' in {tool_name} is not in the user's request (unanswered ask)"
    return "allow", ""


class GuardedToolsExecutor(ToolsExecutor):
    """ToolsExecutor that refuses calls the rule above rejects, returning a BLOCKED tool result to the model."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.blocked_log: list[dict] = []

    def query(self, query, runtime, env=None, messages=(), extra_args=None):
        extra_args = extra_args if extra_args is not None else {}
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1].get("tool_calls"):
            return super().query(query, runtime, env, messages, extra_args) if env is not None else super().query(query, runtime, messages=messages, extra_args=extra_args)
        text = user_request_text(query, messages)
        calls = messages[-1]["tool_calls"]
        verdicts = {c.id: judge(c.function, dict(c.args), text) for c in calls}
        allowed = [c for c in calls if verdicts[c.id][0] == "allow"]
        trimmed = {**messages[-1], "tool_calls": allowed}
        kw = {"env": env} if env is not None else {}
        q, rt, en, msgs, ea = super().query(query, runtime, messages=[*messages[:-1], trimmed], extra_args=extra_args, **kw)
        done = {m["tool_call_id"]: m for m in msgs[len(messages):]}
        out = []
        for c in calls:
            if c.id in done:
                out.append(done[c.id])
            else:
                reason = verdicts[c.id][1]
                self.blocked_log.append({"tool": c.function, "args": dict(c.args), "reason": reason})
                out.append(ChatToolResultMessage(role="tool", content=[text_content_block_from_string(f"BLOCKED: {reason}")],
                                                 tool_call_id=c.id, tool_call=c, error=f"BLOCKED: {reason}"))
        return q, rt, en, [*messages, *out], ea
