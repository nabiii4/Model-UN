"""The AI client's required behavior (BUILD_PROMPT.md sections 9.3, 9.4, 19), with a fake SDK."""
import json
from types import SimpleNamespace

import openai
import pytest

from ai.client import AICapReached, AIClient, AIUnavailable
from ai.schemas import Hint
from config import Config

try:  # the openai SDK uses httpx2 in newer versions and httpx in older ones
    import httpx2 as httpx_mod
except ImportError:  # pragma: no cover
    import httpx as httpx_mod

PRIMARY_KEY = "primarykey-1234567890abcdef"
BACKUP_KEY = "backupkey-1234567890abcdef"
FORBIDDEN = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "logit_bias", "logprobs", "max_tokens"}


def status_error(cls, code, message="error", headers=None):
    req = httpx_mod.Request("POST", "https://example.test/")
    resp = httpx_mod.Response(code, request=req, headers=headers or {})
    return cls(message, response=resp, body={"error": {"message": message}})


def timeout_error():
    return openai.APITimeoutError(request=httpx_mod.Request("POST", "https://example.test/"))


def reply(content, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)])


GOOD = json.dumps({"idea": "Give one real example.", "ask_back": "Who pays for it?"})


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("unexpected extra call")
        action = self.script.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class FakeSDK:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=FakeCompletions(script))


def make_client(primary_script, backup_script=None, with_backup=True, cap=None):
    overrides = {"SKIP_DOTENV": "1", "TESTING": "1", "MOCK_AI": "0",
                 "AZURE_OPENAI_ENDPOINT": "https://primary.example/", "AZURE_OPENAI_API_KEY": PRIMARY_KEY,
                 "AZURE_OPENAI_DEPLOYMENT": "deploy-nano"}
    if with_backup:
        overrides.update({"AZURE_OPENAI_BACKUP_ENDPOINT": "https://backup.example/", "AZURE_OPENAI_BACKUP_API_KEY": BACKUP_KEY})
    else:
        overrides.update({"AZURE_OPENAI_BACKUP_ENDPOINT": "", "AZURE_OPENAI_BACKUP_API_KEY": ""})
    cfg = Config(overrides)
    assert not cfg.mock
    sdks = {"primary": FakeSDK(primary_script), "backup": FakeSDK(backup_script or [])}
    client = AIClient(cfg, sdk_factory=lambda res, media: sdks[res.name], sleep=lambda s: None,
                      cap_provider=(lambda: cap) if cap is not None else None)
    return client, sdks


def ask(client):
    return client.chat_json(feature="chat", system="You are a coach.", convo=[{"role": "user", "content": "hint"}],
                            schema_model=Hint, budget=1200, timeout=5)


def test_never_sends_unsupported_parameters():
    client, sdks = make_client([reply(GOOD)])
    out = ask(client)
    assert out.idea == "Give one real example."
    call = sdks["primary"].chat.completions.calls[0]
    assert not (FORBIDDEN & set(call)), call.keys()
    assert call["max_completion_tokens"] == 1200
    assert call["reasoning_effort"] == "low"
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True


def test_drops_reasoning_effort_after_400_and_remembers():
    err = status_error(openai.BadRequestError, 400, "Unsupported parameter: 'reasoning_effort' is not supported")
    client, sdks = make_client([err, reply(GOOD), reply(GOOD)])
    ask(client)
    calls = sdks["primary"].chat.completions.calls
    assert "reasoning_effort" in calls[0] and "reasoning_effort" not in calls[1]
    ask(client)  # remembered for the rest of the process
    assert "reasoning_effort" not in calls[2]


def test_retries_with_double_budget_on_empty_length_reply():
    client, sdks = make_client([reply("", finish="length"), reply(GOOD)])
    ask(client)
    calls = sdks["primary"].chat.completions.calls
    assert calls[0]["max_completion_tokens"] == 1200
    assert calls[1]["max_completion_tokens"] == 2400


def test_falls_back_from_json_schema_to_json_object():
    err = status_error(openai.BadRequestError, 400, "Invalid schema for response_format 'Hint'")
    client, sdks = make_client([err, reply(GOOD)])
    ask(client)
    calls = sdks["primary"].chat.completions.calls
    assert calls[1]["response_format"] == {"type": "json_object"}
    assert "Return only JSON matching this schema" in calls[1]["messages"][0]["content"]


def test_makes_one_repair_call_on_bad_json():
    client, sdks = make_client([reply("Sure! Here's a hint: be brave."), reply(GOOD)])
    out = ask(client)
    assert out.ask_back == "Who pays for it?"
    calls = sdks["primary"].chat.completions.calls
    assert len(calls) == 2
    assert "did not match the schema" in calls[1]["messages"][-1]["content"]


def test_two_bad_outputs_raise_friendly_error():
    client, _ = make_client([reply("nope"), reply("still nope")])
    with pytest.raises(Exception) as exc:
        ask(client)
    assert getattr(exc.value, "user_message", "")


@pytest.mark.parametrize("make_err", [
    lambda: status_error(openai.RateLimitError, 429, "slow down", {"retry-after": "1"}),
    lambda: status_error(openai.InternalServerError, 500, "boom"),
    lambda: status_error(openai.InternalServerError, 503, "unavailable"),
    timeout_error,
])
def test_fails_over_to_backup(make_err):
    client, sdks = make_client([make_err(), make_err()], [reply(GOOD)])
    out = ask(client)
    assert out.idea
    assert len(sdks["primary"].chat.completions.calls) == 2  # retried the primary once
    assert len(sdks["backup"].chat.completions.calls) == 1
    assert client.failovers_today == 1


def test_both_resources_down_is_ai_unavailable():
    err = lambda: status_error(openai.InternalServerError, 502, "bad gateway")  # noqa: E731
    client, _ = make_client([err(), err()], [err()])
    with pytest.raises(AIUnavailable) as exc:
        ask(client)
    assert "Humans never time out" in exc.value.user_message


def test_401_marks_resource_unhealthy_without_retry():
    client, sdks = make_client([status_error(openai.AuthenticationError, 401, "bad key")], [reply(GOOD), reply(GOOD)])
    ask(client)
    assert len(sdks["primary"].chat.completions.calls) == 1  # no retry on 401
    assert client.resources[0].healthy is False
    ask(client)  # goes straight to the backup next time
    assert len(sdks["primary"].chat.completions.calls) == 1
    rows = client.admin_status()["rows"]
    assert any("Key rejected" in (r["last_error"] or "") for r in rows)


def test_daily_cap():
    client, _ = make_client([reply(GOOD)], cap=1)
    ask(client)
    with pytest.raises(AICapReached):
        ask(client)


def test_admin_errors_never_show_keys_or_endpoints():
    msg = f"Error at https://primary.example/openai with key {PRIMARY_KEY} for deploy-nano"
    client, _ = make_client([status_error(openai.InternalServerError, 500, msg)] * 2, [status_error(openai.InternalServerError, 500, msg)])
    with pytest.raises(AIUnavailable):
        ask(client)
    dump = json.dumps(client.admin_status()) + json.dumps(client.public_health())
    for secret in (PRIMARY_KEY, BACKUP_KEY, "primary.example", "deploy-nano"):
        assert secret not in dump


def test_mock_mode_without_key():
    cfg = Config({"SKIP_DOTENV": "1", "TESTING": "1", "MOCK_AI": "0", "AZURE_OPENAI_API_KEY": "",
                  "AZURE_OPENAI_ENDPOINT": ""})
    assert cfg.mock and cfg.mock_reason == "no key"
    cfg2 = Config({"SKIP_DOTENV": "1", "TESTING": "1", "MOCK_AI": "0", "AZURE_OPENAI_API_KEY": "paste-your-key-here",
                   "AZURE_OPENAI_ENDPOINT": "https://your-resource-name.openai.azure.com/"})
    assert cfg2.mock  # placeholders from .env.example count as "no key"
