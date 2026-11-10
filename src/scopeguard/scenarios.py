"""Build the benchmark suite: harmful scenarios per source, each with a benign twin."""
from __future__ import annotations

import random
from typing import Optional

from . import attackers
from .core import SOURCES, Action, Built, Injection, Scenario, World
from .domains import ALL_FAMILIES, FAMILY_INDEX
from .domains.base import call_tool


def family_of(s: Scenario):
    return FAMILY_INDEX[(s.domain, s.family)]


def build_suite(per_source: int = 100, seed: int = 0) -> list[Scenario]:
    """About `per_source` harmful scenarios per source plus a matching benign twin for each."""
    rng = random.Random(seed)
    out: list[Scenario] = []
    for src in SOURCES:
        fams = [f for f in ALL_FAMILIES if f.source == src]
        base, extra = divmod(per_source, len(fams))
        for fi, fam in enumerate(fams):
            quota = base + (1 if fi < extra else 0)
            chosen: list[tuple[dict, bool]] = [(dict(h), True) for h in fam.hand][:quota]
            seen = {tuple(sorted(c[0].items())) for c in chosen}
            grid = fam.grid()
            rng.shuffle(grid)
            for g in grid:
                if len(chosen) >= quota:
                    break
                key = tuple(sorted(g.items()))
                if key in seen:
                    continue
                seen.add(key)
                chosen.append((g, False))
            for i, (p, hand) in enumerate(chosen):
                sid = f"{fam.domain}.{fam.name}.{i:03d}"
                out.append(Scenario(sid, src, fam.domain, fam.name, False, p, hand))
                out.append(Scenario(sid + ".twin", src, fam.domain, fam.name, True, {**p, "twin": True}, hand))
    return out


def materialize(s: Scenario, injection: Optional[Injection] = None) -> Built:
    return family_of(s).build(dict(s.params), injection)


def attack_injection(s: Scenario, mode: str, seed: int = 0) -> Optional[Injection]:
    """Injection for attacker set 'fixed' (default) or 'mutating'. Adaptive is driven by the runner."""
    if s.source != "A" or s.twin:
        return None
    fam = family_of(s)
    base = fam.default_injection(s.params)
    if mode == "mutating" and base is not None:
        return attackers.mutating_variant(base, seed)
    return base


def run_plan(built: Built, plan: list[dict]) -> World:
    w = built.world.copy()
    for step in plan:
        if "final" in step:
            break
        call_tool(w, built.tools, Action(step["tool"], step.get("args", {})))
    return w


def validate_scenario(s: Scenario) -> list[str]:
    """Invariants every scenario must satisfy. Returns a list of problems (empty = OK)."""
    fam = family_of(s)
    b = materialize(s)
    init = b.world.copy()
    problems = []
    wb = run_plan(b, b.benign_plan)
    if fam.harm(init, wb):
        problems.append(f"benign plan causes harm: {fam.harm(init, wb)}")
    if not fam.done(init, wb):
        problems.append("benign plan does not complete the task")
    if s.twin:
        if b.harm_plans:
            problems.append("twin carries harm plans")
    else:
        if not b.harm_plans:
            problems.append("no harm plans")
        for i, hp in enumerate(b.harm_plans):
            wh = run_plan(b, hp)
            if not fam.harm(init, wh):
                problems.append(f"harm plan {i} causes no harm")
    return problems
