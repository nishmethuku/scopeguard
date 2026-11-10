"""Core data types shared by sandbox, guards, agents and the runner."""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

SOURCES = ("A", "B", "C")  # A attacker, B operator pressure, C overreach
SOURCE_NAMES = {"A": "attacker", "B": "pressure", "C": "overreach"}
DOMAINS = ("booking", "shop", "inbox")


@dataclass
class Mandate:
    """Structured record of what the user authorized. None means 'not specified'."""

    goal: str
    allowed_tools: Optional[list[str]] = None
    spend_limit: Optional[float] = None
    allowed_recipients: Optional[list[str]] = None
    allowed_endpoints: Optional[list[str]] = None
    resources: Optional[list[str]] = None  # extra owner-scoped things the user may touch
    max_quantity: Optional[int] = None
    requested: list[str] = field(default_factory=list)  # items / add-ons the user explicitly asked for

    def vague(self) -> "Mandate":
        """A mandate that captured the goal but none of the limits."""
        return Mandate(goal=self.goal)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Mandate":
        return Mandate(**d)


@dataclass
class Action:
    tool: str
    args: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"tool": self.tool, "args": self.args}


@dataclass
class Effects:
    """What an action touches. Produced by the tool, read by guards."""

    side_effect: bool = False
    reversible: bool = True
    spend: float = 0.0
    quantity: int = 0
    recipients: list[str] = field(default_factory=list)  # emails / payees / message targets
    endpoints: list[str] = field(default_factory=list)  # URL hosts
    writes: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, id, owner)
    reads: list[tuple[str, str]] = field(default_factory=list)  # (kind, owner)
    charges: list[tuple[str, float]] = field(default_factory=list)  # (label, amount) add-ons
    grounded: dict[str, str] = field(default_factory=dict)  # arg name -> entity value needing provenance
    violations: list[str] = field(default_factory=list)  # service-policy rules this action would break
    text: str = ""  # free text the user will read (reply) or that leaves the system


@dataclass
class Verdict:
    decision: str  # allow | ask | block
    reason: str = ""
    layer: str = ""
    model_calls: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class World:
    domain: str
    data: dict
    outbox: list = field(default_factory=list)  # replies shown to the user
    calls: list = field(default_factory=list)  # executed tool calls
    egress: list = field(default_factory=list)  # attempted outside-network URLs (always refused)

    def copy(self) -> "World":
        return copy.deepcopy(self)

    def snapshot(self) -> str:
        return json.dumps({"domain": self.domain, "data": self.data}, sort_keys=True)


@dataclass
class Tool:
    name: str
    description: str
    params: list[str]
    run: Callable[[World, dict], tuple[str, bool]]  # -> (observation, trusted)
    effects: Callable[[World, dict], Effects]


@dataclass
class Injection:
    loc: str  # email_body | page | calendar | tool_desc | notice | review
    parts: list[str]  # one part per carrier document; >1 means split
    goal: str = ""
    style: str = ""


@dataclass
class Built:
    """A concrete, runnable scenario instance."""

    world: World
    tools: dict[str, Tool]
    user_task: str
    mandate: Mandate
    operator_prompt: str
    benign_plan: list[dict]
    harm_plans: list[list[dict]]
    injection: Optional[Injection] = None


@dataclass
class Scenario:
    id: str
    source: str
    domain: str
    family: str
    twin: bool
    params: dict
    hand: bool = True  # template written by hand (vs. grid-generated variant)

    def to_dict(self) -> dict:
        return asdict(self)
