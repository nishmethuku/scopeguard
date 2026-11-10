"""60-second demo: one scenario three ways (no guard, injection-tuned guard, ScopeGuard) plus its harmless twin.

Uses the simulated agent forced to follow the injection, so the page shows how the GUARDS behave on a fixed
harmful action sequence. It does not say how often any real model would follow the injection.
"""
from __future__ import annotations

import html
import json

from .agents.policies import SimAgent, SimProfile
from .guards import make_guard
from .runner import RunConfig, run_episode
from .scenarios import build_suite

FORCE = SimProfile(p_attack_base=1.0, p_pressure=1.0, p_overreach=1.0, persist=0.0)


def pick(suite):
    agent = SimAgent(FORCE)
    by_id = {s.id: s for s in suite}
    for s in suite:
        if s.twin or s.source != "A" or not s.hand:
            continue
        res = {g: run_episode(s, agent, make_guard(g), 0, RunConfig()) for g in ("none", "classifier", "l1+l2+ask")}
        tw = run_episode(by_id[s.id + ".twin"], agent, make_guard("l1+l2+ask"), 0, RunConfig())
        if res["none"]["harm"] and res["classifier"]["harm"] and not res["l1+l2+ask"]["harm"] and tw["task_done"] and not tw["harm"] \
                and all(st["executed"] for st in tw["steps"]):
            return s, res, tw
    raise RuntimeError("no suitable demo scenario found")


def render(suite=None) -> str:
    suite = suite or build_suite()
    s, res, tw = pick(suite)
    titles = {"none": "1. No guard", "classifier": "2. Injection-tuned guard", "l1+l2+ask": "3. ScopeGuard"}

    def col(title, tr, verdict):
        rows = []
        for st in tr["steps"]:
            cls = "ok" if st["executed"] else "blocked"
            mark = "" if not st["harmful"] else " harmful"
            a = st["action"]
            rows.append(f'<li class="{cls}{mark}"><code>{html.escape(a["tool"])}({html.escape(json.dumps(a["args"])[:90])})</code>'
                        f'{"<span> BLOCKED: " + html.escape(st["reason"][:110]) + "</span>" if not st["executed"] else ""}</li>')
        return f'<section><h2>{title}</h2><ol>{"".join(rows)}</ol><p class="v {"bad" if tr["harm"] else "good"}">{verdict}</p></section>'

    cols = "".join(col(titles[g], res[g], "Harm occurred: " + ", ".join(res[g]["harm_kinds"]) if res[g]["harm"] else "No harm. Task completed." if res[g]["task_done"] else "No harm.") for g in res)
    twin = col("Same task, harmless content, with ScopeGuard", tw, "No false blocks. Task completed." if tw["task_done"] else "Task not completed.")
    return f"""<!doctype html><meta charset="utf-8"><title>ScopeGuard demo</title>
<style>body{{font:15px system-ui;margin:2rem;max-width:1200px}}h1{{font-size:1.3rem}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}}
section{{border:1px solid #ccc;border-radius:8px;padding:.8rem}}li{{margin:.3rem 0;list-style-position:inside}}li.harmful code{{background:#fde2e2}}li.blocked span{{color:#a40;font-size:.85em}}
li.blocked code{{text-decoration:line-through}}.v{{font-weight:600}}.bad{{color:#b00}}.good{{color:#070}}code{{font-size:.85em}}.note{{color:#555}}</style>
<h1>ScopeGuard demo: {html.escape(s.id)}</h1>
<p>User task: <em>{html.escape(run_user_task(s))}</em></p>
<p class="note">A third party hid an instruction in content the agent reads. The simulated agent below is forced to follow it, so this page shows how each guard handles the same harmful action. It does not measure how often a real model falls for it.</p>
<div class="grid">{cols}</div><h2>The harmless twin</h2><div class="grid">{twin}</div>"""


def run_user_task(s):
    from .scenarios import materialize
    return materialize(s).user_task
