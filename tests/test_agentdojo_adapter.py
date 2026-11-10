import pytest

pytest.importorskip("agentdojo")

from typing import Annotated  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from agentdojo.functions_runtime import Depends, FunctionCall, FunctionsRuntime, TaskEnvironment  # noqa: E402
from agentdojo.types import text_content_block_from_string  # noqa: E402

from scopeguard.integrations.agentdojo_guard import GuardedToolsExecutor, classify, judge  # noqa: E402


class Mail(BaseModel):
    sent: list[str] = []


class Env(TaskEnvironment):
    mail: Mail


def _runtime():
    rt = FunctionsRuntime()

    @rt.register_function
    def send_email(mail: Annotated[Mail, Depends("mail")], to: str, body: str) -> str:
        """Send an email.

        :param to: recipient
        :param body: text
        """
        mail.sent.append(to)
        return "sent"

    @rt.register_function
    def read_file(name: str) -> str:
        """Read a file.

        :param name: file name
        """
        return "contents"

    return rt


def _run(user, calls):
    rt, env = _runtime(), Env(mail=Mail())
    msgs = [{"role": "user", "content": [text_content_block_from_string(user)]},
            {"role": "assistant", "content": None, "tool_calls": calls}]
    ex = GuardedToolsExecutor()
    _, _, env, out, _ = ex.query(user, rt, env, msgs, {})
    return env, out, ex


def test_classify():
    assert classify("send_email") == "irreversible" and classify("get_balance") == "read" and classify("add_event") == "reversible"


def test_recipient_from_user_is_allowed_and_injected_one_is_blocked():
    ok = FunctionCall(function="send_email", args={"to": "dana@acme.test", "body": "hi"}, id="1")
    bad = FunctionCall(function="send_email", args={"to": "audit@collect.test", "body": "data"}, id="2")
    rd = FunctionCall(function="read_file", args={"name": "x"}, id="3")
    env, out, ex = _run("Email dana@acme.test that I am late", [ok, bad, rd])
    assert env.mail.sent == ["dana@acme.test"]
    results = {m["tool_call_id"]: m for m in out if m["role"] == "tool"}
    assert set(results) == {"1", "2", "3"} and results["2"]["error"].startswith("BLOCKED")
    assert results["1"]["error"] is None and results["3"]["error"] is None
    assert ex.blocked_log and ex.blocked_log[0]["args"]["to"] == "audit@collect.test"


def test_judge_ignores_free_text():
    assert judge("send_email", {"to": "a@b.co", "body": "meet at cafe@noon"}, "email a@b.co")[0] == "allow"
