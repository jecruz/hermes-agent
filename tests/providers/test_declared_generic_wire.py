"""A ``providers:`` entry can opt a profile-less built-in provider into the generic (custom) wire policy.

Built-in keyless overlays such as ``llmdynamix`` have no provider profile, and a built-in name
shadows a same-named ``providers:`` entry for routing, so the bare-named-custom fallback never
applied: a configured ``agent.reasoning_effort`` never reached the endpoint and the route's own
default silently applied. ``providers.<name>.wire_profile: custom`` opts the route into the
generic profile, whose ``reasoning_effort`` the endpoint receives.
"""
from __future__ import annotations

import json
import logging

import pytest
from openai import OpenAI

import providers
from agent.transports.chat_completions import ChatCompletionsTransport
from providers import get_provider_profile
from tests.fakes.providers.chat_variants import CText, FakeChatVariantServer

BUILTIN_WITHOUT_PROFILE = "llmdynamix"


@pytest.fixture(autouse=True)
def _fresh_warning_state(monkeypatch):
    """The once-per-route warning keeps process-wide state; every test starts with it empty."""
    import agent.chat_completion_helpers as helpers

    monkeypatch.setattr(helpers, "_REASONING_NOT_SENT_WARNED", set())


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated HERMES_HOME whose config.yaml the test writes (JSON is valid YAML), with the name memo cleared."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(providers, "_NAMED_CUSTOM_MEMO", {})
    monkeypatch.setattr(providers, "_NAMED_CUSTOM_MEMO_SIG", {})

    def write(entry: dict | None) -> None:
        providers_block = {BUILTIN_WITHOUT_PROFILE: {"base_url": "http://127.0.0.1:12444/v1", **(entry or {})}}
        (tmp_path / "config.yaml").write_text(json.dumps({"providers": providers_block}), encoding="utf-8")

    return write


def test_builtin_provider_without_profile_keeps_the_legacy_wire_by_default(home):
    home(None)
    assert get_provider_profile(BUILTIN_WITHOUT_PROFILE) is None


def test_wire_profile_custom_opts_the_builtin_provider_into_the_generic_profile(home):
    home({"wire_profile": "custom"})
    assert get_provider_profile(BUILTIN_WITHOUT_PROFILE) is get_provider_profile("custom")


@pytest.mark.parametrize("value", ["openrouter", "nous", "", None, True, ["custom"]])
def test_only_the_custom_value_is_accepted(home, value):
    home({"wire_profile": value})
    assert get_provider_profile(BUILTIN_WITHOUT_PROFILE) is None


def test_an_unreadable_config_keeps_the_legacy_wire_and_says_why(home, monkeypatch, caplog):
    home({"wire_profile": "custom"})
    monkeypatch.setattr("hermes_cli.config.is_provider_enabled", lambda entry: 1 / 0)
    with caplog.at_level(logging.WARNING):
        assert get_provider_profile(BUILTIN_WITHOUT_PROFILE) is None
    assert any("wire_profile" in r.getMessage() for r in caplog.records)


def test_a_disabled_entry_does_not_opt_in(home):
    home({"wire_profile": "custom", "enabled": False})
    assert get_provider_profile(BUILTIN_WITHOUT_PROFILE) is None


def test_the_opt_in_never_overrides_a_registered_profile(home):
    home({"wire_profile": "custom"})
    assert get_provider_profile("openrouter") is not get_provider_profile("custom")


def test_configured_effort_reaches_the_wire_through_the_opted_in_profile(home):
    """End to end over HTTP: the loopback server records the body the OpenAI client sent."""
    home({"wire_profile": "custom"})
    profile = get_provider_profile(BUILTIN_WITHOUT_PROFILE)
    with FakeChatVariantServer([CText("ok")]) as server:
        kwargs = ChatCompletionsTransport().build_kwargs(
            "gpt-6.1-sol", [{"role": "user", "content": "hi"}], tools=None, provider_profile=profile,
            reasoning_config={"enabled": True, "effort": "high"}, base_url=server.base_url,
        )
        stream = OpenAI(base_url=server.base_url, api_key="none").chat.completions.create(stream=True, **kwargs)
        list(stream)
        bodies = [record["body"] for record in server.requests]
    assert [body.get("reasoning_effort") for body in bodies] == ["high"]


def test_without_the_opt_in_the_same_effort_never_reaches_the_wire(home):
    home(None)
    with FakeChatVariantServer([CText("ok")]) as server:
        kwargs = ChatCompletionsTransport().build_kwargs(
            "gpt-6.1-sol", [{"role": "user", "content": "hi"}], tools=None,
            provider_profile=get_provider_profile(BUILTIN_WITHOUT_PROFILE),
            reasoning_config={"enabled": True, "effort": "high"}, base_url=server.base_url,
            model_lower="gpt-6.1-sol", provider_name=BUILTIN_WITHOUT_PROFILE,
        )
        list(OpenAI(base_url=server.base_url, api_key="none").chat.completions.create(stream=True, **kwargs))
        bodies = [record["body"] for record in server.requests]
    assert [body.get("reasoning_effort") for body in bodies] == [None]


def test_a_configured_effort_that_goes_nowhere_is_logged_once(home, caplog):
    from agent.chat_completion_helpers import warn_reasoning_effort_not_sent

    home(None)
    agent = type("Agent", (), {"provider": BUILTIN_WITHOUT_PROFILE, "model": "gpt-6.1-sol"})()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            warn_reasoning_effort_not_sent(agent, {"enabled": True, "effort": "high"}, supports_reasoning=False)
    messages = [r.getMessage() for r in caplog.records if "reasoning effort" in r.getMessage()]
    assert len(messages) == 1 and "wire_profile: custom" in messages[0]


def test_the_warning_is_scoped_to_the_owning_profile_home(tmp_path, monkeypatch, caplog):
    from agent.chat_completion_helpers import warn_reasoning_effort_not_sent

    agent = type("Agent", (), {"provider": BUILTIN_WITHOUT_PROFILE, "model": "gpt-6.1-sol"})()
    with caplog.at_level(logging.WARNING):
        for profile_home in ("a", "a", "b"):
            monkeypatch.setenv("HERMES_HOME", str(tmp_path / profile_home))
            warn_reasoning_effort_not_sent(agent, {"enabled": True, "effort": "high"}, supports_reasoning=False)
    assert len([r for r in caplog.records if "reasoning effort" in r.getMessage()]) == 2


def test_nothing_is_logged_when_the_effort_is_sent_or_unset(home, caplog):
    from agent.chat_completion_helpers import warn_reasoning_effort_not_sent

    home(None)
    agent = type("Agent", (), {"provider": "zzz-quiet", "model": "m"})()
    with caplog.at_level(logging.WARNING):
        warn_reasoning_effort_not_sent(agent, None, supports_reasoning=False)
        warn_reasoning_effort_not_sent(agent, {"enabled": True, "effort": "high"}, supports_reasoning=True)
    assert [r for r in caplog.records if "reasoning effort" in r.getMessage()] == []
