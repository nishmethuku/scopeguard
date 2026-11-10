import json

from scopeguard.agents.policies import SimAgent
from scopeguard.guards import make_guard
from scopeguard.metrics import fmt, paired_bootstrap, summarize, wilson
from scopeguard.runner import RunConfig, load_traces, run_episode, run_grid
from scopeguard import prereg


def _strip(t):
    return {k: v for k, v in t.items() if k not in ("ts", "guard_ms")} | {"steps": [{k: v for k, v in s.items()} for s in t["steps"]]}


def test_runs_are_deterministic(small):
    agent, g = SimAgent(), make_guard("l1+l2+ask")
    for s in small[:40]:
        assert _strip(run_episode(s, agent, g, 3, RunConfig())) == _strip(run_episode(s, agent, g, 3, RunConfig()))


def test_grid_resumes_without_duplicates(small, tmp_path):
    p = str(tmp_path / "t.jsonl")
    n1 = run_grid(small, SimAgent(), ["none", "l1"], [0], p)
    n2 = run_grid(small, SimAgent(), ["none", "l1"], [0], p)
    assert n1 == len(small) * 2 and n2 == 0
    assert len(load_traces(p)) == n1


def test_action_level_harm_labels_match_state(small):
    agent = SimAgent()
    for s in small:
        t = run_episode(s, agent, make_guard("none"), 0, RunConfig())
        executed_harm = any(st["harmful"] and st["executed"] for st in t["steps"])
        assert executed_harm == t["harm"] or t["twin"], s.id


def test_summarize_has_all_columns(small, tmp_path):
    p = str(tmp_path / "t.jsonl")
    run_grid(small, SimAgent(), ["none", "l1+l2+ask"], [0, 1], p)
    rows = summarize(load_traces(p))
    assert set(rows) == {"none", "l1+l2+ask"}
    assert {"block_A", "false_block", "task_completion", "escalations_per_100"} <= set(rows["none"])


def test_wilson_and_bootstrap():
    p, lo, hi = wilson(50, 100)
    assert abs(p - 0.5) < 1e-9 and 0.39 < lo < 0.41 and 0.59 < hi < 0.61
    assert fmt(0, 0) == "n/a"
    a = {f"s{i}": (1, 1) for i in range(30)}
    b = {f"s{i}": (0, 1) for i in range(30)}
    d, lo, hi = paired_bootstrap(a, b, reps=200)
    assert d == 1.0 and lo == 1.0


def test_prereg_lock_detects_changes(small, tmp_path):
    pre, lock = tmp_path / "p.json", tmp_path / "l.json"
    pre.write_text(json.dumps({"false_block_limit": 0.05}))
    assert not prereg.is_confirmatory(small, str(pre), str(lock))
    prereg.freeze(small, str(pre), str(lock))
    assert prereg.is_confirmatory(small, str(pre), str(lock))
    pre.write_text(json.dumps({"false_block_limit": 0.5}))
    assert not prereg.is_confirmatory(small, str(pre), str(lock))
    prereg.freeze(small, str(pre), str(lock))
    assert not prereg.is_confirmatory(small[:-2], str(pre), str(lock))
