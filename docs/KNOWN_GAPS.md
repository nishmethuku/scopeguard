# Known gaps of the offline guard

Found by attacking the guard myself. Each item is either covered by a test or listed as a limit to state in any write-up.

| Gap | Status |
|---|---|
| Short ids were "grounded" by accidental substring matches (`c2` inside `abc2`; an address inside a longer lookalike). | **Fixed**: whole-token matching, with a test. |
| A tool's confirmation ("added 3 x g1 to cart") counted as trusted evidence for the injected value. | **Fixed** earlier: results of side-effecting calls cannot vouch for arguments. |
| Cart contents were not checked at checkout, so an item added earlier slipped through. | **Fixed**: checkout lists every cart item as an argument to ground. |
| Paraphrased false claims ("a couple of seats remain", "you will not get in without the pass") evade the regex claim detectors. | **Open**, `xfail(strict)` test. This is what the LLM judge is for. |
| Data leaked inside the body of a message to an *allowed* recipient is not inspected. The oracles do not score it either. | **Open**, not modeled. |
| An injected action that the user's words make plausible (user says "clean up my inbox", injection says delete invoices) passes the intent check. | **Open**, inherent to intent matching. |
| The simulated user approves exactly the harmless actions. | **Limit**, state it. |
| The heuristic judge was written against these scenario families, so its scores here are optimistic by construction. | **Limit**, use `--judge` and E5. |
