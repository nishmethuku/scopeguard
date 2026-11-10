import json

import pytest

pytest.importorskip("pydantic")

from scopeguard.integrations.doomarena_guard import ScopeGuardSafetyCheck, tool_calls_of  # noqa: E402


def call(name, **args):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


USER = {"role": "user", "content": "Email the report to boss@corp.test please"}


def test_parses_tool_calls():
    assert tool_calls_of(call("send_email", to="a@b.test")) == [("send_email", {"to": "a@b.test"})]


def test_user_supplied_recipient_passes_and_injected_one_is_flagged():
    d = ScopeGuardSafetyCheck()
    assert d.attack_detected([USER, call("send_email", to="boss@corp.test")]) is False
    assert d.attack_detected([USER, call("send_email", to="audit@collect.test")]) is True


def test_reads_and_plain_messages_are_not_flagged():
    d = ScopeGuardSafetyCheck()
    assert d.attack_detected([USER, call("get_balance")]) is False
    assert d.attack_detected([USER]) is False


def test_defense_name_and_real_base_class():
    assert ScopeGuardSafetyCheck().defense_name == "scopeguard"
    base = pytest.importorskip("doomarena.core.agent_defenses.base")
    assert isinstance(ScopeGuardSafetyCheck(), base.AttackSafetyCheck)
