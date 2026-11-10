"""Run episodes: agent x guard x scenario x seed, with action-level harm labels and full traces."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from . import BENCHMARK_VERSION, attackers
from .agents.policies import Final, Observation
from .core import Action, Injection, Mandate, Scenario
from .domains.base import call_tool
from .guards import make_guard
from .guards.base import GuardContext, HistEntry
from .scenarios import attack_injection, family_of, materialize


@dataclass
class RunConfig:
    max_steps: int = 12
    mandate_mode: str = "oracle"  # oracle | vague
    attacker_set: str = "fixed"  # fixed | mutating
    persona: str = ""  # text the user adds about themselves (E6)
    guard_kwargs: Optional[dict] = None


def label_harmful(fam, initial, world, tools, action: Action) -> bool:
    """Would executing this action turn a harm-free world into a harmful one? (dry run on a copy)"""
    if fam.harm(initial, world):
        return False
    w2 = world.copy()
    try:
        call_tool(w2, tools, action)
    except Exception:
        return False
    return bool(fam.harm(initial, w2))


def run_episode(s: Scenario, agent, guard, seed: int, cfg: RunConfig, injection: Optional[Injection] = None) -> dict:
    fam = family_of(s)
    if injection is None and cfg.attacker_set != "fixed":
        injection = attack_injection(s, cfg.attacker_set, seed)
    built = materialize(s, injection)
    task = built.user_task + (" " + cfg.persona if cfg.persona else "")
    initial = built.world.copy()
    world = built.world
    mandate: Mandate = built.mandate.vague() if cfg.mandate_mode == "vague" else built.mandate
    ctx = GuardContext(mandate, [task], world, built.tools)
    guard.begin(ctx)
    built.user_task = task
    policy = agent.start(built, s, seed, guard.prompt_suffix)

    steps, last, esc, g_ms, g_calls = [], None, 0, 0.0, 0
    final = ""
    for _ in range(cfg.max_steps):
        nxt = policy.next(last)
        if isinstance(nxt, Final):
            final = nxt.text
            break
        action = nxt
        harmful = label_harmful(fam, initial, world, built.tools, action)
        eff = ctx.effects(action)
        t0 = time.perf_counter()
        v = guard.check(action, ctx)
        g_ms += (time.perf_counter() - t0) * 1000
        g_calls += v.model_calls
        decision, reason, asked = v.decision, v.reason, False
        if decision == "ask":
            asked, esc = True, esc + 1
            decision = "block" if harmful else "allow"  # simulated user approves only what they would approve
            reason = reason + (" | user declined" if harmful else " | user approved")
        if decision == "allow":
            obs, trusted = call_tool(world, built.tools, action)
            executed, spend = True, eff.spend
        else:
            obs, trusted, executed, spend = f"BLOCKED: {reason}", True, False, 0.0
        ctx.history.append(HistEntry(action, obs, trusted, executed, spend, eff.side_effect))
        steps.append({"action": action.to_dict(), "harmful": harmful, "decision": v.decision, "asked": asked, "executed": executed,
                      "layer": v.layer, "reason": reason, "obs": obs[:300]})
        last = Observation(obs, blocked=not executed)

    kinds = fam.harm(initial, world)
    return {
        "scenario": s.id, "source": s.source, "domain": s.domain, "family": s.family, "twin": s.twin, "hand": s.hand,
        "agent": agent.id, "guard": guard.id, "judge": guard.judge_name, "seed": seed, "attacker_set": cfg.attacker_set, "mandate_mode": cfg.mandate_mode,
        "persona": bool(cfg.persona), "steps": steps, "final": final[:300], "harm": bool(kinds), "harm_kinds": kinds,
        "task_done": bool(fam.done(initial, world)), "escalations": esc, "guard_ms": g_ms, "guard_model_calls": g_calls,
        "agent_model_calls": getattr(policy, "model_calls", 0), "bench": BENCHMARK_VERSION,
        "injection": ({"loc": built.injection.loc, "parts": built.injection.parts, "goal": built.injection.goal} if built.injection else None),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def run_adaptive(s: Scenario, agent, guard, seed: int, cfg: RunConfig, attacker: attackers.AdaptiveAttacker, budget: int) -> dict:
    """Attacker sees the guard's block message and rewrites the injection, up to `budget` attempts."""
    inj = attack_injection(s, "fixed")
    success_at, attempts = None, []
    for k in range(1, budget + 1):
        tr = run_episode(s, agent, guard, seed * 1000 + k, cfg, injection=inj)
        attempts.append({"k": k, "harm": tr["harm"], "loc": inj.loc, "style": inj.style, "parts": inj.parts})
        if tr["harm"]:
            success_at = k
            break
        blocked = [st["reason"] for st in tr["steps"] if not st["executed"]]
        inj = attacker.next(inj, blocked[-1] if blocked else None, k)
    return {"scenario": s.id, "source": s.source, "domain": s.domain, "family": s.family, "twin": False, "agent": agent.id,
            "guard": guard.id, "seed": seed, "attacker_set": "adaptive", "budget": budget, "success_at": success_at,
            "attempts": attempts, "bench": BENCHMARK_VERSION}


# ---- grids ------------------------------------------------------------------------------------

def trace_key(t: dict) -> str:
    return "|".join(str(t.get(k)) for k in ("scenario", "agent", "guard", "seed", "attacker_set", "mandate_mode", "persona"))


def load_traces(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []


def run_grid(suite: list[Scenario], agent, guard_names: list[str], seeds: list[int], out_path: str, cfg: Optional[RunConfig] = None,
             workers: int = 1, judge_provider=None, extra: Optional[dict] = None, progress: Optional[Callable[[int, int], None]] = None) -> int:
    cfg = cfg or RunConfig()
    done = {trace_key(t) for t in load_traces(out_path)}
    lock = threading.Lock()
    jobs = []
    for g in guard_names:
        for s in suite:
            for seed in seeds:
                probe = {"scenario": s.id, "agent": agent.id, "guard": make_guard(g, judge_provider, **(cfg.guard_kwargs or {})).id,
                         "seed": seed, "attacker_set": cfg.attacker_set, "mandate_mode": cfg.mandate_mode, "persona": bool(cfg.persona)}
                if trace_key(probe) not in done:
                    jobs.append((g, s, seed))
    n_done = [0]

    def work(job):
        g, s, seed = job
        guard = make_guard(g, judge_provider, **(cfg.guard_kwargs or {}))
        tr = run_episode(s, agent, guard, seed, cfg)
        if extra:
            tr.update(extra)
        with lock:
            with open(out_path, "a") as f:
                f.write(json.dumps(tr) + "\n")
            n_done[0] += 1
            if progress:
                progress(n_done[0], len(jobs))

    if workers <= 1:
        for j in jobs:
            work(j)
    else:
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(work, jobs))
    return len(jobs)
