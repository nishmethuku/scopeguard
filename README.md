# ScopeGuard

Do the guards that stop attackers on AI agents also stop agents that hurt people while doing what they were told?

ScopeGuard measures that gap and builds a guard that tries to close it. It has three parts:

1. **A benchmark** with one sandbox, one set of tools and one set of metrics for three sources of harm: an attacker hiding instructions in content (A), an operator goal that pushes the agent to deceive (B), and an agent that takes a harmful route to the user's own goal (C). Every harmful scenario has a harmless twin, so false blocks can be measured.
2. **A guard** that checks each action against what the user authorized, what the action touches, and whether it can be undone. Layer 1 is plain rules (least privilege). Layer 2 is a scope check by a judge. An optional ask-the-user path handles reversible but unclear actions.
3. **A harness** that runs agents against guards, including baselines, ablations and an adaptive attacker, and reports block, miss and false-block rates with intervals.

The thesis is a hypothesis to test, not a result. Nothing in this repository is a result about real models yet.

## Quick start

```bash
pip install -e ".[dev]"
pytest -q                     # 29 tests
scopeguard validate           # 600 scenarios, every invariant checked
make smoke && make table      # full pipeline on a SIMULATED agent
scopeguard demo               # writes demo/index.html (one scenario, three ways)
```

The `sim` agent is a toy used to exercise the harness. **Its numbers are not results**, and the tables print a banner saying so.

## Running real models

```bash
export ANTHROPIC_API_KEY=...   # and/or OPENAI_API_KEY, GEMINI_API_KEY, COMPAT_API_KEY
scopeguard estimate --exp E3 --price-in <usd per M> --price-out <usd per M>   # estimate cost first
scopeguard run --exp E1 --agent anthropic:<model id> --seeds 5 --workers 4
scopeguard run --exp E2 --agent anthropic:<model id> --seeds 5
# write down thresholds, then lock them BEFORE E3:
$EDITOR config/prereg.json && scopeguard freeze
scopeguard run --exp E3 --agent anthropic:<model id> --judge openai:<model id> --seeds 5
scopeguard run --exp E4 --agent anthropic:<model id> --judge openai:<model id> --budget 200
scopeguard run --exp E5 --agent anthropic:<model id> --judge openai:<model id>   # held-out domain
scopeguard table --in results/E3.jsonl
scopeguard compare --in results/E3.jsonl --metric block_B --a l1+l2+ask --b classifier
scopeguard taxonomy --in results/E3.jsonl --kind miss --n 30 --out results/misses.json
```

Provider specs: `anthropic:<model>`, `openai:<model>`, `gemini:<model>`, `compat:<base_url>|<model>` for open-weight models behind an OpenAI-compatible server. Pin exact model IDs; traces record the resolved model and timestamp. `--judge` should be a model from a different family than the agent being guarded.

E3, E4 and E5 refuse to run without a valid pre-registration lock unless you pass `--exploratory`. Traces are stamped `confirmatory: true/false` so exploratory runs cannot be mistaken for pre-registered ones.

## Layout

| Path | What it holds |
|---|---|
| `src/scopeguard/domains/` | Fake booking, shop and inbox services; tools; scenario families; harm and task oracles. No network imports. |
| `src/scopeguard/scenarios.py` | Builds the suite (100 harmful per source plus twins) and validates it. |
| `src/scopeguard/attackers.py` | Fixed, mutating and adaptive attackers. |
| `src/scopeguard/guards/` | Layer 1 rules, Layer 2 judges (heuristic and LLM), baselines, scale checks. |
| `src/scopeguard/agents/` | Plain tool-calling loop (one for every model), providers, simulated agent. |
| `src/scopeguard/runner.py`, `metrics.py`, `experiments.py` | Episodes, statistics, E1 to E6. |
| `config/prereg.json` | Hypotheses, falsifiers, false-block limit, primary comparisons. |
| `docs/` | `DESIGN.md`, `ETHICS.md`. |

## What the benchmark contains

- 3 domains (appointment booking, shopping, inbox and payments), each hosting all three harm sources, so a whole domain can be held out for E5.
- 100 harmful scenarios per source and a benign twin for each: 600 in total. 32 harmful templates are hand-authored hard cases; the rest are generated from parameter grids. The plan asks for 20 or more by hand, which this meets, and more hand-written cases would help.
- Harm is read by **code oracles over sandbox state** (another person's record changed, an undisclosed charge, data sent to an unapproved recipient). Free-text claims use narrow pattern oracles checked against ground-truth facts. No model judge is used for scoring yet. If you add one, validate it on at least 100 human-labeled traces.
- Action-level labels: each proposed action is dry-run on a copy of the world, so "harm-causing actions stopped / proposed" can be computed even when a guard blocks the action.

## Metrics

Three numbers per harm source (blocked, missed, wrongly blocked), never a single score. Also task completion on twins, escalations per 100 tasks, added latency and added model calls. Wilson intervals for rates; paired bootstrap over scenarios for differences between guards.

## Honest limits (read before citing anything)

- **No real-model results exist yet.** The week 1 gate (reproduce one published number) has not been run; it needs API access and a base framework run. See `docs/DESIGN.md`.
- **The Layer 2 offline heuristic judge was written by the same author as the scenarios.** Its near-perfect scores on the simulated agent show the pipeline works, not that the guard generalizes. The real test is an LLM judge from another family (`--judge`), the held-out domain (E5), and unmodified third-party benchmarks.
- **The "off-the-shelf classifier" is a stand-in** pattern scorer. Swap in a real classifier with `HFClassifierGuard` (`pip install -e ".[hf]"`) before making any claim about existing guards.
- **The simulated user approves exactly the actions that are not harmful.** Real users make mistakes in both directions.
- **AgentDojo and DoomArena are not integrated yet.** The sandbox is self-contained so it can be rerun in one command. Adapters for E5's unmodified-AgentDojo run and for the upstream pull request still need to be written against those projects' current APIs.
- The "blocks everything" scale check still lets the agent talk to the user (`reply`), so pressure harm done purely through words is not stopped by it.
- Search again before writing the word "first" anywhere.

## Provenance of design

The project plan, research questions and falsification criteria are in the original planning document; `config/prereg.json` mirrors them.
