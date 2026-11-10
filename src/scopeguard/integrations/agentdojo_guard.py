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

from typing import Any

from scopeguard.integrations.generic import (  # noqa: F401  (re-exported for callers and tests)
    EMAIL, IBAN, IRREVERSIBLE, READ_VERBS, RECIPIENT_ARGS, URL, classify, judge, recipient_values)
from agentdojo.agent_pipeline import ToolsExecutor
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.types import ChatToolResultMessage, text_content_block_from_string

def user_request_text(query: str, messages) -> str:
    parts = [query or ""]
    for m in messages:
        if m.get("role") == "user":
            parts += [b.get("content", "") for b in (m.get("content") or []) if isinstance(b, dict)]
    return "\n".join(parts).lower()


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
