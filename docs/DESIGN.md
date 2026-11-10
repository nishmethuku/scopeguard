# Design notes

## Threat model

The same harmful outcome (money moved, a record changed, a misleading statement) can come from three sources, and a guard needs different evidence for each.

| | A. Attacker | B. Operator pressure | C. Overreach |
|---|---|---|---|
| Who pushes the agent | A third party who wrote content the agent reads | The deployer, through a business goal | Nobody; the agent picks the means |
| Evidence the guard can use | Untrusted content shaped the action | A claim contradicts the system's own records | The action exceeds what the user could authorize |

Out of scope: chatbot jailbreaks that produce bad text, training-time attacks, real systems of any kind.

## Pipeline

```
agent proposes action
   -> dry run on a copy of the world -> action-level harm label (for scoring only; guards never see it)
   -> guard.check(action, ctx)        ctx = user messages, structured mandate, tool effects, history, deployer records
        Layer 1 (rules)  tool allowlist, spend and quantity caps, recipient and endpoint allowlists,
                         no writes or reads of records the user does not own, service-policy violations
        Layer 2 (scope)  does the mandate cover it / who else is affected / can it be undone
                         -> allow | ask | block, with a reason
   -> ask: simulated user approves iff the action is not harmful (friction is counted)
   -> block: the agent sees "BLOCKED: <reason>" (the adaptive attacker sees it too)
   -> allow: the tool runs in the sandbox; state changes
oracle(initial_world, final_world) -> harm kinds ; done(...) -> task completed
```

## Decisions worth knowing

- **Provenance.** Layer 2 grounds every entity in a side-effecting action (recipient, class id, item, address, cart contents). An entity found only in third-party text is blocked. The result of a side-effecting call is not accepted as evidence, because tool confirmations echo the agent's own arguments ("added 3 x g1 to cart") and would launder an injected value. A test covers this; the first draft had the bug.
- **Guards cannot see labels.** They get no scenario family, source, twin flag or oracle. They do read the deployer's own records (inventory, fees, refund eligibility, which user is authenticated), as a deployed policy engine would.
- **Mandate capture is the weak point.** `--mandate vague` strips every limit from the mandate to measure the damage (Layer 1 loses almost all its rules; Layer 2 loses extra resources the user was granted, which shows up as false blocks).
- **Twins differ in content, not surface.** Same tools, same wording, harmless content: a fee the user asked for, a truthful scarcity claim, a refusal that is correct, an email that contains the word "ignore".
- **Sim agent.** Follows a scripted benign or harmful plan with arbitrary probabilities. It exists to test the plumbing: determinism, resume, scoring, tables. It is stamped SIMULATED everywhere.

## Gates for the four-week plan

1. Sandbox closed (tests pass, container has no outside network for offline runs); reproduce one published number with a real framework; cost per run estimated. *Not done here: needs API access.*
2. Scenarios, twins and oracles built and validated (`scopeguard validate`); 100 traces hand-labeled if any model judge is used; E1 run; hypotheses and the false-block limit frozen (`scopeguard freeze`). *Scenarios, oracles and tooling done.*
3. Baselines, Layer 1, Layer 2, ablations, E2 to E4; read 30 misses and 30 false blocks (`scopeguard taxonomy`). *Code done; real runs not done.*
4. E5, paper, README, demo, results file; an outsider reruns the table from this README. *Code, README and demo done.*
