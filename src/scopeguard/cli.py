"""scopeguard command line."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from . import BENCHMARK_VERSION, experiments, prereg
from .agents import LLMAgent, SimAgent, make_provider
from .metrics import adaptive_curve, failure_sample, harm_rate_markdown, headline_markdown, paired_bootstrap, per_scenario, block_nd, falseblock_nd
from .runner import load_traces
from .scenarios import build_suite, validate_scenario


def get_agent(spec: str, rpm: float = 0.0, max_calls: int = 0):
    return SimAgent() if spec == "sim" else LLMAgent(make_provider(spec, rpm, max_calls))


def cmd_validate(a):
    suite = build_suite(a.per_source, a.seed)
    bad = {s.id: p for s in suite if (p := validate_scenario(s))}
    c = Counter((s.source, s.twin) for s in suite)
    hand = sum(1 for s in suite if s.hand and not s.twin)
    print(f"benchmark {BENCHMARK_VERSION}: {len(suite)} scenarios ({hand} hand-authored harmful, "
          + ", ".join(f"{k[0]}{'-twin' if k[1] else ''}={v}" for k, v in sorted(c.items())) + ")")
    for sid, p in bad.items():
        print("INVALID", sid, p)
    return 1 if bad else 0


def cmd_freeze(a):
    suite = build_suite(a.per_source, a.seed)
    print(json.dumps(prereg.freeze(suite), indent=2))


def cmd_run(a):
    suite = build_suite(a.per_source, a.seed)
    os.makedirs(a.out, exist_ok=True)
    agent = get_agent(a.agent, a.rpm, a.max_calls)
    seeds = list(range(a.seeds))
    judge = make_provider(a.judge, a.rpm, a.max_calls) if a.judge else None
    conf = prereg.is_confirmatory(suite)
    if a.exp in ("E3", "E4", "E5") and not conf and not a.exploratory:
        print("No valid pre-registration lock. Edit config/prereg.json, run `scopeguard freeze`, or pass --exploratory.", file=sys.stderr)
        return 2
    if a.exp == "E5":
        for dom in ("booking", "shop", "inbox"):
            print(dom, "->", experiments.tune_and_holdout(suite, agent, seeds, a.out, dom, prereg.load()["false_block_limit"], a.workers, judge))
        return 0
    fn = experiments.EXPERIMENTS[a.exp]
    kw = dict(workers=a.workers, judge_provider=judge)
    if a.guards:
        kw["guards"] = a.guards.split(",")
    if a.exp == "E3":
        kw["mandate_mode"] = a.mandate
    if a.exp == "E4":
        kw = dict(budget=a.budget, judge_provider=judge, attacker_provider=make_provider(a.attacker, a.rpm, a.max_calls) if a.attacker else None)
    n = fn(suite, agent, seeds, a.out, **kw)
    print(f"{a.exp}: ran {n} new episodes ({'confirmatory' if conf else 'EXPLORATORY'}) -> {a.out}")
    if a.agent == "sim":
        print("NOTE: agent 'sim' is a pipeline-test simulator. Do not report these numbers.")
    return 0


def cmd_table(a):
    ts = load_traces(a.inp)
    if any(t.get("attacker_set") == "adaptive" for t in ts):
        for g, cur in adaptive_curve(ts).items():
            print(g, {b: f"{k}/{n}" for b, (k, n) in cur.items()})
        return 0
    print(headline_markdown(ts, a.agent))
    print()
    print(harm_rate_markdown(ts, a.agent))


def cmd_compare(a):
    ts = [t for t in load_traces(a.inp) if t.get("attacker_set") != "adaptive"]
    f = {"block_A": ("A", block_nd), "block_B": ("B", block_nd), "block_C": ("C", block_nd), "false_block": (None, falseblock_nd)}[a.metric]
    def sel(g):
        return per_scenario([t for t in ts if t["guard"] == g and ((f[0] is None and t["twin"]) or (f[0] and t["source"] == f[0] and not t["twin"]))], f[1])
    d, lo, hi = paired_bootstrap(sel(a.a), sel(a.b), reps=prereg.load()["bootstrap_reps"])
    print(f"{a.metric}: {a.a} minus {a.b} = {100*d:+.1f} pp  [95% bootstrap over scenarios: {100*lo:+.1f}, {100*hi:+.1f}]")


def cmd_taxonomy(a):
    s = failure_sample(load_traces(a.inp), a.kind, a.n)
    with open(a.out, "w") as f:
        json.dump(s, f, indent=1)
    print(f"wrote {len(s)} {a.kind} cases to {a.out}; fill in each 'cause' by hand")


def cmd_estimate(a):
    suite = build_suite(a.per_source, a.seed)
    guards = {"E1": 1, "E2": 4, "E3": 9}[a.exp]
    episodes = len(suite) * guards * a.seeds
    calls = episodes * a.steps
    cost = calls * (a.tokens_in * a.price_in + a.tokens_out * a.price_out) / 1e6
    print(f"{a.exp}: {episodes} episodes x ~{a.steps} agent calls = {calls} calls per model; est ${cost:,.0f} per model "
          f"at ${a.price_in}/M in, ${a.price_out}/M out (prices are your inputs; check current rates)")


def cmd_demo(a):
    from .demo import render
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        f.write(render(build_suite(a.per_source, a.seed)))
    print("wrote", a.out)


def main(argv=None):
    p = argparse.ArgumentParser("scopeguard")
    p.add_argument("--per-source", type=int, default=100)
    p.add_argument("--seed", type=int, default=0, help="suite construction seed")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)
    sub.add_parser("freeze").set_defaults(fn=cmd_freeze)
    r = sub.add_parser("run")
    r.add_argument("--exp", required=True, choices=["E1", "E2", "E3", "E4", "E5", "E6"])
    r.add_argument("--agent", default="sim", help="sim | anthropic:<model> | openai:<model> | compat:<url>|<model> | gemini:<model>")
    r.add_argument("--judge", default=None, help="provider spec for the Layer 2 model judge (default: offline heuristic judge)")
    r.add_argument("--attacker", default=None, help="provider spec for an LLM adaptive attacker (default: rule-based)")
    r.add_argument("--seeds", type=int, default=3)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--budget", type=int, default=200)
    r.add_argument("--mandate", default="oracle", choices=["oracle", "vague"])
    r.add_argument("--out", default="results")
    r.add_argument("--guards", default=None, help="comma list to run a subset of guards in E2/E3, e.g. none,classifier,l1+l2+ask")
    r.add_argument("--rpm", type=float, default=0.0, help="max requests per minute per provider (stay under a free tier's limit)")
    r.add_argument("--max-calls", type=int, default=0, help="hard cap on requests per provider for this invocation; runs resume where they stopped")
    r.add_argument("--exploratory", action="store_true")
    r.set_defaults(fn=cmd_run)
    t = sub.add_parser("table")
    t.add_argument("--in", dest="inp", required=True)
    t.add_argument("--agent", default=None)
    t.set_defaults(fn=cmd_table)
    c = sub.add_parser("compare")
    c.add_argument("--in", dest="inp", required=True)
    c.add_argument("--metric", required=True, choices=["block_A", "block_B", "block_C", "false_block"])
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.set_defaults(fn=cmd_compare)
    x = sub.add_parser("taxonomy")
    x.add_argument("--in", dest="inp", required=True)
    x.add_argument("--kind", choices=["miss", "false_block"], required=True)
    x.add_argument("--n", type=int, default=30)
    x.add_argument("--out", required=True)
    x.set_defaults(fn=cmd_taxonomy)
    e = sub.add_parser("estimate")
    e.add_argument("--exp", choices=["E1", "E2", "E3"], default="E3")
    e.add_argument("--seeds", type=int, default=3)
    e.add_argument("--steps", type=float, default=6)
    e.add_argument("--tokens-in", type=int, default=1500)
    e.add_argument("--tokens-out", type=int, default=120)
    e.add_argument("--price-in", type=float, required=True, help="USD per million input tokens")
    e.add_argument("--price-out", type=float, required=True, help="USD per million output tokens")
    e.set_defaults(fn=cmd_estimate)
    d = sub.add_parser("demo")
    d.add_argument("--out", default="demo/index.html")
    d.set_defaults(fn=cmd_demo)
    a = p.parse_args(argv)
    from .agents.providers import ProviderError
    try:
        return a.fn(a) or 0
    except ProviderError as e:
        print(f"stopped: {e}\nTraces so far are saved; rerun the same command to resume.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
