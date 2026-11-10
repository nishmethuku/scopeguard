"""Guard interface and the context every guard sees.

A guard never sees scenario labels (source, family, twin) or oracle code. It sees what a
deployed guard could see: the user's messages, the structured mandate, tool effects,
conversation history and read access to the deployer's own records.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core import Action, Effects, Mandate, Tool, Verdict, World


@dataclass
class HistEntry:
    action: Action
    obs: str
    trusted: bool
    executed: bool
    spend: float = 0.0
    side_effect: bool = False


class GuardContext:
    def __init__(self, mandate: Mandate, user_messages: list[str], world: World, tools: dict[str, Tool]):
        self.mandate = mandate
        self.user_messages = user_messages
        self.world = world
        self.tools = tools
        self.history: list[HistEntry] = []
        self.user_id: str = world.data.get("user", "")

    def effects(self, action: Action) -> Effects:
        tool = self.tools.get(action.tool)
        if tool is None:
            return Effects(side_effect=True, reversible=False)
        try:
            return tool.effects(self.world, action.args)
        except Exception:
            return Effects(side_effect=True, reversible=False)

    def spent(self) -> float:
        return sum(h.spend for h in self.history if h.executed)

    def untrusted_obs(self) -> list[str]:
        return [h.obs for h in self.history if not h.trusted]

    def prior_replies(self) -> list[str]:
        return [str(h.action.args.get("text", "")) for h in self.history if h.executed and h.action.tool == "reply"]

    def user_text(self) -> str:
        m = self.mandate
        parts = list(self.user_messages) + [m.goal] + list(m.requested)
        parts += list(m.allowed_recipients or []) + list(m.allowed_endpoints or []) + list(m.resources or [])
        return "\n".join(parts).lower()

    def trusted_text(self) -> str:
        # Echoes of side-effecting calls ("added 3 x g1 to cart") repeat the agent's own arguments, so they
        # cannot vouch for those arguments. Only read-only trusted results count as grounding evidence.
        return self.user_text() + "\n" + "\n".join(h.obs.lower() for h in self.history if h.trusted and not h.side_effect)


class Guard:
    id = "base"
    prompt_suffix = ""
    judge_name = ""

    def begin(self, ctx: GuardContext) -> None:
        pass

    def check(self, action: Action, ctx: GuardContext) -> Verdict:
        return Verdict("allow", "", self.id)
