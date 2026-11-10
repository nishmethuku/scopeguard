"""ScopeGuard: Layer 1 rules, then Layer 2 scope check, with optional ask-the-user."""
from __future__ import annotations

from ..core import Action, Verdict
from .base import Guard, GuardContext
from .judge import HeuristicJudge
from .rules import RuleGuard


class ScopeGuard(Guard):
    def __init__(self, layer1: bool = True, layer2: bool = True, ask: bool = True, judge=None):
        self.l1 = RuleGuard() if layer1 else None
        self.l2 = (judge or HeuristicJudge()) if layer2 else None
        self.ask = ask
        self.judge_name = getattr(self.l2, "name", "") if self.l2 is not None else ""
        self.id = "+".join(x for x, on in (("l1", layer1), ("l2", layer2), ("ask", ask and layer2)) if on) or "none"

    def check(self, action: Action, ctx: GuardContext) -> Verdict:
        if self.l1 is not None:
            v = self.l1.check(action, ctx)
            if v.decision != "allow":
                return Verdict(v.decision, v.reason, "l1")
        if self.l2 is not None:
            d, reason, calls = self.l2.judge(action, ctx)
            if d == "ask" and not self.ask:
                d, reason = "block", reason + " (no ask-the-user: treated as block)"
            return Verdict(d, reason, "l2", model_calls=calls)
        return Verdict("allow", "", self.id)
