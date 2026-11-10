"""Layer 1: rules. No model involved. This is also the least-privilege baseline."""
from __future__ import annotations

from ..core import Action, Verdict
from .base import Guard, GuardContext


class RuleGuard(Guard):
    id = "l1"

    def check(self, action: Action, ctx: GuardContext) -> Verdict:
        m = ctx.mandate
        if action.tool == "reply":
            return Verdict("allow", "", self.id)
        eff = ctx.effects(action)
        if m.allowed_tools is not None and action.tool not in m.allowed_tools:
            return Verdict("block", f"tool '{action.tool}' is not in the allowed tools for this task", self.id)
        if m.spend_limit is not None and ctx.spent() + eff.spend > m.spend_limit + 1e-9:
            return Verdict("block", f"spend ${ctx.spent() + eff.spend:.2f} would exceed the ${m.spend_limit:.2f} limit", self.id)
        if m.max_quantity is not None and eff.quantity > m.max_quantity:
            return Verdict("block", f"quantity {eff.quantity} exceeds the allowed {m.max_quantity}", self.id)
        if m.allowed_recipients is not None:
            allow = {r.lower() for r in m.allowed_recipients}
            for r in eff.recipients:
                if r.lower() not in allow:
                    return Verdict("block", f"recipient '{r}' is not on the allowlist", self.id)
        if m.allowed_endpoints is not None:
            allow = {e.lower() for e in m.allowed_endpoints}
            for e in eff.endpoints:
                if e.lower() not in allow:
                    return Verdict("block", f"endpoint '{e}' is not on the allowlist", self.id)
        owned = {ctx.user_id} | set(m.resources or [])
        for kind, ident, owner in eff.writes:
            if owner not in owned:
                return Verdict("block", f"writes a {kind} record owned by '{owner}', not the user", self.id)
        for kind, owner in eff.reads:
            if owner not in owned:
                return Verdict("block", f"reads {kind} data owned by '{owner}', not the user", self.id)
        if eff.violations:
            return Verdict("block", "breaks a service rule: " + "; ".join(eff.violations), self.id)
        return Verdict("allow", "", self.id)
