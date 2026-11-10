# Running ScopeGuard for free

Everything except calls to hosted models is free. You have three zero-cost ways to get real model behavior. Check each provider's current free limits yourself, because they change.

## Option 1: a model on your own computer (no account, no limits)

Install Ollama (https://ollama.com), pull a small model, and point the harness at its OpenAI-compatible server:

```bash
ollama pull <a small instruct model>          # 3B to 8B models run on a normal laptop
scopeguard --per-source 20 run --exp E1 --agent "compat:http://localhost:11434/v1|<model name>" --seeds 1
```

Small models follow the JSON tool protocol less reliably. If many runs end early, that is a finding about the model, not a bug; the trace shows what it said.

## Option 2: free API tiers

Several providers offer a free tier with an API key and no card (for example Google AI Studio for Gemini, Groq, OpenRouter's free models, GitHub Models). Use them through the harness:

```bash
export GEMINI_API_KEY=...
scopeguard --per-source 20 run --exp E1 --agent gemini:<model id> --seeds 1 --rpm 10 --max-calls 900
# OpenAI-compatible free endpoints:
export COMPAT_API_KEY=...
scopeguard --per-source 20 run --exp E1 --agent "compat:<base url>|<model id>" --seeds 1 --rpm 10 --max-calls 900
```

- `--rpm` spaces requests so you stay under the per-minute limit.
- `--max-calls` stops the run before you pass a daily quota. Traces are saved after every episode, so run the same command the next day and it resumes.
- Free tiers may log prompts. The benchmark contains only fake data, so that is fine here.

## Option 3: spend nothing and still make progress

These need no model at all and are already working: `scopeguard validate`, the simulated pipeline (`make smoke`), the demo page, and every guard that does not call a model (Layer 1, the heuristic Layer 2, the classifier stand-in).

## Keeping a real run small

The agent is the cost: each episode is about 5 to 8 model calls. With `--per-source 20` there are 120 scenarios (60 harmful, 60 twins).

| Run | Episodes (1 seed) | Rough agent calls |
|---|---|---|
| E1, no guard | 120 | 700 to 900 |
| E2 subset: `--guards none,classifier,l1` | 360 | 2,000 to 3,000 |
| E3 subset: `--guards none,classifier,l1,l1+l2+ask` | 480 | 3,000 to 4,000 |

Suggested order: E1, then E3 with the four-guard subset (this answers the main question), then E4 on a smaller budget (`--budget 15`). Keep the Layer 2 judge on the offline heuristic (the default) so the guard adds zero model calls. A model judge doubles the calls and is the first thing to drop on a free tier.

Pre-registration still applies: freeze before E3, or pass `--exploratory` and say so.

Smaller suites give wider intervals. Say the suite size in any write-up.
