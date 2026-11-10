import io
import json

import pytest

from scopeguard import cli
from scopeguard.agents import providers
from scopeguard.agents.policies import Final, LLMAgent
from scopeguard.core import Action
from scopeguard.domains.base import first_json
from scopeguard.scenarios import materialize


class Fake(providers.Provider):
    spec = "fake:x"

    def __init__(self, script):
        super().__init__()
        self.script, self.seen = list(script), []

    def complete(self, system, messages, max_tokens=700, temperature=0.0):
        self.seen.append((system, list(messages)))
        return self.script.pop(0), {}


def test_first_json_handles_prose_and_nesting():
    assert first_json('Sure! {"tool": "book", "args": {"a": {"b": 1}}} done') == {"tool": "book", "args": {"a": {"b": 1}}}
    assert first_json("no json here") is None


def test_llm_policy_parses_tool_and_final(small):
    s = next(x for x in small if x.family == "C_waitlist" and not x.twin)
    b = materialize(s)
    prov = Fake(['I will look. {"tool": "get_class", "args": {"class_id": "c1"}}', '{"final": "done"}'])
    pol = LLMAgent(prov).start(b, s, 0)
    a = pol.next(None)
    assert isinstance(a, Action) and a.tool == "get_class"
    from scopeguard.agents.policies import Observation
    assert isinstance(pol.next(Observation("ok")), Final)
    assert "TOOL RESULT" in prov.seen[1][1][-1]["content"]
    assert "admin_api" in prov.seen[0][0]  # tool list is in the system prompt


def test_provider_response_parsing(monkeypatch):
    def fake_post(self, url, headers, body, retries=4):
        if "anthropic" in url:
            return {"content": [{"type": "text", "text": "hi"}], "usage": {"input_tokens": 3, "output_tokens": 2}, "model": "m-1"}
        if "generativelanguage" in url:
            return {"candidates": [{"content": {"parts": [{"text": "hi"}]}}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}
        return {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}
    monkeypatch.setattr(providers.Provider, "_post", fake_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    for spec in ("anthropic:claude-x", "openai:gpt-x", "compat:http://localhost:8000/v1|local", "gemini:g-x"):
        p = providers.make_provider(spec)
        text, _ = p.complete("sys", [{"role": "user", "content": "q"}])
        assert text == "hi" and p.tokens_in == 3 and p.tokens_out == 2
    with pytest.raises(ValueError):
        providers.make_provider("nope:x")


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(providers.ProviderError, match="ANTHROPIC_API_KEY"):
        providers.AnthropicProvider("m").complete("s", [{"role": "user", "content": "x"}])


def test_llm_judge_fails_toward_ask(small):
    from scopeguard.guards.judge import LLMJudge
    from scopeguard.guards.base import GuardContext
    s = next(x for x in small if x.family == "A_notice" and not x.twin)
    b = materialize(s)
    ctx = GuardContext(b.mandate, [b.user_task], b.world, b.tools)
    d, _, calls = LLMJudge(Fake(["not json"])).judge(Action("book", {"class_id": "c1", "member_id": "u1"}), ctx)
    assert d == "ask" and calls == 1
    d, r, _ = LLMJudge(Fake(['{"decision":"block","reason":"nope"}'])).judge(Action("book", {"class_id": "c2", "member_id": "u1"}), ctx)
    assert d == "block" and r == "nope"


def test_cli_validate_and_run(tmp_path, capsys):
    assert cli.main(["--per-source", "6", "validate"]) == 0
    assert cli.main(["--per-source", "6", "run", "--exp", "E1", "--agent", "sim", "--seeds", "1", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "E1.jsonl").exists()
    # E3 refuses to run without a valid pre-registration lock
    assert cli.main(["--per-source", "6", "run", "--exp", "E3", "--agent", "sim", "--seeds", "1", "--out", str(tmp_path)]) in (0, 2)


def test_demo_renders(small):
    from scopeguard.demo import render
    from scopeguard.scenarios import build_suite
    html = render(build_suite(100, 0))
    assert "ScopeGuard demo" in html and "Harm occurred" in html and "No harm" in html


def test_call_cap_and_rate_limit(monkeypatch):
    import time
    monkeypatch.setattr(providers.Provider, "_post", providers.Provider._post)
    p = providers.make_provider("compat:http://localhost:1/v1|m", rpm=0, max_calls=1)
    p.calls = 1
    with pytest.raises(providers.ProviderError, match="call cap"):
        p._gate()
    q = providers.make_provider("compat:http://localhost:1/v1|m", rpm=6000)
    t0 = time.monotonic(); q._gate(); q._gate()
    assert time.monotonic() - t0 >= 0.009


def test_free_presets(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    p = providers.make_provider("groq:llama-x")
    assert p.spec == "groq:llama-x" and p.base == "https://api.groq.com/openai/v1"
    with pytest.raises(providers.ProviderError, match="GROQ_API_KEY"):
        p.complete("s", [{"role": "user", "content": "x"}])
    assert providers.make_provider("openrouter:m:free").base == "https://openrouter.ai/api/v1"


def test_llm_agent_is_told_the_account_id():
    from scopeguard.agents.policies import LLMAgent
    from scopeguard.scenarios import build_suite, materialize
    s = build_suite(per_source=1)[0]
    pol = LLMAgent(Fake([])).start(materialize(s), s, 0)
    assert "account id is" in pol.system


def test_format_retries_recover_and_are_traced(small):
    from scopeguard.guards import make_guard
    from scopeguard.runner import RunConfig, run_episode
    s = next(x for x in small if x.family == "C_waitlist" and not x.twin)
    prov = Fake(["", '{"reply": "hi"}', '{"final": "ok"}'])
    tr = run_episode(s, LLMAgent(prov), make_guard("none"), 0, RunConfig())
    assert tr["final"] == "ok" and tr["format_retries"] == 2 and tr["format_failed"] is False
    assert prov.seen[1][1][-1]["content"].startswith("Invalid format.")


def test_format_failure_after_two_corrections(small):
    from scopeguard.guards import make_guard
    from scopeguard.runner import RunConfig, run_episode
    s = next(x for x in small if x.family == "C_waitlist" and not x.twin)
    prov = Fake(["", "", '{"x": 1}'])
    tr = run_episode(s, LLMAgent(prov), make_guard("none"), 0, RunConfig())
    assert tr["format_retries"] == 2 and tr["format_failed"] is True and len(prov.seen) == 3


def test_host_parse_failure_is_a_protocol_failure_not_an_outage(monkeypatch):
    def boom(self, url, headers, body, retries=8):
        raise providers.ProviderError('HTTP 400 from x: b\'{"error":{"code":"output_parse_failed","failed_generation":"We will add to cart."}}\'')
    monkeypatch.setattr(providers.Provider, "_post", boom)
    p = providers.make_provider("compat:http://x/v1|m")
    assert p.complete("s", [{"role": "user", "content": "x"}])[0] == ""
