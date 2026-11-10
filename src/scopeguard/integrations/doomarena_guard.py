"""ScopeGuard as a DoomArena defense (`AttackSafetyCheck`).

DoomArena defenses receive the chat history as a list of message dicts and answer one question: is an attack present.
This adapter reads the most recent assistant tool call(s) from that history (OpenAI/litellm shape:
`tool_calls[i]["function"]["name"]` and a JSON string `arguments`) and applies the same provenance rule used for
AgentDojo (`integrations/generic.py`): a side-effecting call whose recipient-like argument does not appear in the
user's own messages is flagged. Read-only calls are never flagged.

    from scopeguard.integrations.doomarena_guard import ScopeGuardSafetyCheck
    defense = ScopeGuardSafetyCheck()

Status: unit-tested on the message shape above and on the real `AttackSafetyCheck` base class. It has not been run
inside a DoomArena gateway on a real benchmark, and DoomArena's own message shape for tool calls should be confirmed
before relying on it. This is the simple rule only (no Layer 2 judge and no mandate); report utility next to attack success.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel

from scopeguard.integrations.generic import judge

try:  # use DoomArena's real base class when it is installed
    from doomarena.core.agent_defenses.base import AttackSafetyCheck as _Base
except ImportError:  # pragma: no cover
    _Base = BaseModel


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c.get("text") if isinstance(c, dict) else c) for c in content)
    return ""


def tool_calls_of(message: dict) -> list[tuple[str, dict]]:
    out = []
    for c in message.get("tool_calls") or []:
        fn = c.get("function", c) if isinstance(c, dict) else {}
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {}
        out.append((fn.get("name", ""), args if isinstance(args, dict) else {}))
    return out


class ScopeGuardSafetyCheck(_Base):
    defense_name: Literal["scopeguard"] = "scopeguard"
    abort_on_detection: bool = True

    def attack_detected(self, messages: list[dict[str, Any]]) -> bool:
        last = next((m for m in reversed(messages) if m.get("role") == "assistant" and m.get("tool_calls")), None)
        if last is None:
            return False
        user_text = "\n".join(_text(m.get("content")) for m in messages if m.get("role") == "user").lower()
        return any(judge(name, args, user_text)[0] != "allow" for name, args in tool_calls_of(last))
