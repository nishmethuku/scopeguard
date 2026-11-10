# Containment and responsible release

Containment comes first. The Hugging Face incident in the project plan happened because a test environment was not as sealed as intended.

## What is sealed, and how

- **Sandbox services are in-process fake classes.** The modules in `src/scopeguard/domains/` import no network library. `tests/test_suite.py::test_sandbox_imports_no_network_libs` fails the build if one is added.
- **`fetch_url` never leaves the process.** Known fake hosts return canned pages. Any other URL is recorded in `world.egress`, refused, and counted as harm by the oracle.
- **Every attacker address is on the reserved `.test` TLD**, which never resolves.
- **Fake credentials only.** The one password in the benchmark opens a fake mailbox. Keep no real keys on the machine that runs experiments, other than the model API keys the harness needs.
- **Only the harness process calls model APIs.** It sends text to a provider and receives text back. Tools run inside the sandbox, so a model cannot cause a network request by itself.

## Running

- Simulated and offline runs: `docker run --network none scopeguard ...`.
- Runs that call a model API need outbound network for the harness. Restrict egress to the provider hosts you use (firewall or proxy allowlist) and review logs for anything else.
- Every action is logged in the JSONL traces. Search them for `egress` or for tool names outside the registry; treat any such attempt as a finding.
- Never point an agent at a real website, booking system or account, even for a quick check.

## People

- No human subjects. Personas (E6) are simulated users. Results describe model behavior, not how real vulnerable people fare.
- Personas are defined by what the user states, and always compared with a matched control, so the result is a measured difference.

## Provider rules and disclosure

- Read each provider's usage policy and check for a red-teaming or research program before running attacks at scale.
- If a model shows a serious failure that is not already public, tell the vendor first and follow its disclosure process before publishing details.
- Release the benchmark, harness and guard. Release attack generators with care: ship the templates needed to reproduce the paper and hold back anything more useful to an attacker than to a defender. The adaptive attacker here is a rewrite loop over fake targets and is not tuned against any real product.

## Limits to state in any write-up

Simulated services, a finite set of scenarios, models that change over time, a guard tested only against the attackers built here, and a simulated user that approves exactly the actions that are not harmful.
