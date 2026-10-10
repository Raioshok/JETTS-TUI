"""Behavior tests for the Antigravity (Cloud Code v1internal) client facade."""

from __future__ import annotations

import json

import httpx
import pytest

from agent.antigravity_adapter import (
    SKIP_THOUGHT_SIGNATURE,
    AntigravityClient,
    adapt_request_for_model,
    unwrap_response,
    wrap_request,
)
from agent.gemini_native_adapter import GeminiAPIError, build_gemini_request

TOOLS = [
    {"type": "function", "function": {"name": "mcp.lookup", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "terminal", "parameters": {
        "type": "object", "properties": {"command": {"type": "string"}}}}},
]
PARALLEL_HISTORY = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "a", "function": {"name": "mcp.lookup", "arguments": "{}"}},
        {"id": "b", "function": {"name": "terminal", "arguments": "{\"command\": \"ls\"}"}},
    ]},
    {"role": "tool", "tool_call_id": "a", "content": "one"},
    {"role": "tool", "tool_call_id": "b", "content": "two"},
]


def _creds(**overrides):
    def source(force_refresh: bool = False):
        source.calls.append(force_refresh)
        token = "tok-refreshed" if force_refresh else "tok-1"
        return {"api_key": token, "project_id": "proj-1", **overrides}

    source.calls = []
    return source


def _client(handler, **kwargs):
    return AntigravityClient(
        base_url="https://daily-cloudcode-pa.sandbox.googleapis.com",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        credential_source=kwargs.pop("credential_source", _creds()),
        **kwargs,
    )


def _gemini_payload(parts, finish="STOP"):
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2, "totalTokenCount": 5}}


def test_claude_calls_and_responses_pair_by_id_and_parallel_calls_drop_signature():
    request = adapt_request_for_model(build_gemini_request(messages=PARALLEL_HISTORY, tools=TOOLS),
                                      "claude-sonnet-4-6")
    model_turn = next(c for c in request["contents"] if c["role"] == "model")
    calls = [p for p in model_turn["parts"] if "functionCall" in p]
    responses = [p["functionResponse"] for c in request["contents"] for p in c["parts"] if "functionResponse" in p]

    assert [c["functionCall"]["id"] for c in calls] == [r["id"] for r in responses]
    assert calls[0]["thoughtSignature"] == SKIP_THOUGHT_SIGNATURE
    assert all("thoughtSignature" not in c for c in calls[1:])
    # Claude rejects dots in tool names; every declared name is valid.
    names = [d["name"] for t in request["tools"] for d in t["functionDeclarations"]]
    assert all(n.replace("_", "").replace("-", "").isalnum() for n in names)
    assert {c["functionCall"]["name"] for c in calls} <= set(names)


def test_claude_thinking_budget_fits_under_max_output_tokens():
    request = adapt_request_for_model(
        build_gemini_request(messages=PARALLEL_HISTORY, max_tokens=1000),
        "claude-opus-4-6-thinking",
        thinking_config={"includeThoughts": True, "thinkingBudget": 32768},
        max_tokens_explicit=True,
    )
    config = request["generationConfig"]
    assert config["thinkingConfig"]["include_thoughts"] is True
    assert config["maxOutputTokens"] > config["thinkingConfig"]["thinking_budget"]


def test_gemini_pro_tier_in_model_id_overrides_thinking_level():
    request = adapt_request_for_model(
        build_gemini_request(messages=PARALLEL_HISTORY, thinking_config={"includeThoughts": True, "thinkingLevel": "low"}),
        "gemini-3-pro-high",
    )
    assert request["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "high"


def test_envelope_round_trip():
    body = wrap_request({"contents": []}, model="gemini-3-flash", project_id="p", session_id="s")
    assert body["project"] == "p" and body["model"] == "gemini-3-flash"
    assert body["request"]["sessionId"] == "s"
    assert unwrap_response({"response": {"candidates": []}}) == {"candidates": []}


def test_non_streaming_request_is_wrapped_and_tool_names_restored():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"response": _gemini_payload(
            [{"functionCall": {"name": "mcp_lookup", "args": {}, "id": "x"}}])})

    result = _client(handler).chat.completions.create(model="claude-sonnet-4-6", messages=PARALLEL_HISTORY[:2], tools=TOOLS)

    assert seen["url"].endswith("/v1internal:generateContent")
    assert seen["auth"] == "Bearer tok-1"
    assert seen["body"]["project"] == "proj-1"
    assert seen["body"]["model"] == "claude-sonnet-4-6"
    assert result.choices[0].message.tool_calls[0].function.name == "mcp.lookup"


def test_unauthorized_forces_one_refresh_then_succeeds():
    tokens = []

    def handler(request: httpx.Request) -> httpx.Response:
        tokens.append(request.headers["authorization"])
        if len(tokens) == 1:
            return httpx.Response(401, json={"error": {"message": "expired", "status": "UNAUTHENTICATED"}})
        return httpx.Response(200, json={"response": _gemini_payload([{"text": "ok"}])})

    source = _creds()
    result = _client(handler, credential_source=source).chat.completions.create(
        model="gemini-3-flash", messages=PARALLEL_HISTORY[:2])

    assert result.choices[0].message.content == "ok"
    assert tokens == ["Bearer tok-1", "Bearer tok-refreshed"]
    assert source.calls == [False, True]


def test_falls_back_to_next_endpoint_on_unavailable_backend():
    hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if len(hosts) == 1:
            return httpx.Response(503, json={"error": {"message": "down"}})
        return httpx.Response(200, json={"response": _gemini_payload([{"text": "ok"}])})

    _client(handler).chat.completions.create(model="gemini-3-flash", messages=PARALLEL_HISTORY[:2])
    assert len(hosts) == 2 and hosts[0] != hosts[1]


def test_rate_limit_is_not_retried_on_other_endpoints():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return httpx.Response(429, json={"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})

    with pytest.raises(GeminiAPIError) as exc_info:
        _client(handler).chat.completions.create(model="gemini-3-flash", messages=PARALLEL_HISTORY[:2])
    assert exc_info.value.status_code == 429
    assert len(calls) == 1


QUOTA_EXHAUSTED_BODY = {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED", "details": [
    {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "QUOTA_EXHAUSTED",
     "metadata": {"quotaResetDelay": "3h2m4.5s"}},
]}}
BURST_LIMIT_BODY = {"error": {"code": 429, "message": "slow down", "status": "RESOURCE_EXHAUSTED", "details": [
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "2s"},
]}}


def _switching_accounts():
    """Credential source + rotator pair backed by a list of account tokens."""
    state = {"active": 0, "rotations": []}
    tokens = ["tok-a", "tok-b"]

    def source(force_refresh: bool = False):
        return {"api_key": tokens[state["active"]], "project_id": f"proj-{state['active']}"}

    def rotator(retry_after):
        state["rotations"].append(retry_after)
        if state["active"] + 1 >= len(tokens):
            return False
        state["active"] += 1
        return True

    return source, rotator, state


@pytest.mark.parametrize("stream", [False, True])
def test_drained_quota_switches_to_the_next_saved_account(stream):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        if request.headers["authorization"] == "Bearer tok-a":
            return httpx.Response(429, json=QUOTA_EXHAUSTED_BODY)
        if stream:
            body = f"data: {json.dumps({'response': _gemini_payload([{'text': 'ok'}])})}\n\n"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"response": _gemini_payload([{"text": "ok"}])})

    source, rotator, state = _switching_accounts()
    result = _client(handler, credential_source=source, account_rotator=rotator).chat.completions.create(
        model="gemini-3-flash", messages=PARALLEL_HISTORY[:2], stream=stream)
    if stream:
        text = "".join(c.choices[0].delta.content or "" for c in result)
    else:
        text = result.choices[0].message.content
    assert text == "ok"
    assert seen == ["Bearer tok-a", "Bearer tok-b"]
    assert state["rotations"] == [pytest.approx(3 * 3600 + 2 * 60 + 4.5)]


def test_short_burst_limit_does_not_switch_accounts():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json=BURST_LIMIT_BODY)

    source, rotator, state = _switching_accounts()
    with pytest.raises(GeminiAPIError) as exc_info:
        _client(handler, credential_source=source, account_rotator=rotator).chat.completions.create(
            model="gemini-3-flash", messages=PARALLEL_HISTORY[:2])
    assert exc_info.value.status_code == 429
    assert state["rotations"] == []


def test_every_account_drained_surfaces_the_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json=QUOTA_EXHAUSTED_BODY)

    source, rotator, state = _switching_accounts()
    with pytest.raises(GeminiAPIError) as exc_info:
        _client(handler, credential_source=source, account_rotator=rotator).chat.completions.create(
            model="gemini-3-flash", messages=PARALLEL_HISTORY[:2])
    assert exc_info.value.status_code == 429
    assert len(state["rotations"]) == 2 and state["active"] == 1


def test_streaming_unwraps_sse_events():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":streamGenerateContent")
        events = [
            {"response": _gemini_payload([{"text": "Hel"}], finish="")},
            {"response": _gemini_payload([{"text": "lo"}])},
        ]
        body = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    chunks = list(_client(handler).chat.completions.create(
        model="gemini-3-flash", messages=PARALLEL_HISTORY[:2], stream=True))
    text = "".join(c.choices[0].delta.content or "" for c in chunks)
    assert text == "Hello"
    assert chunks[-1].choices[0].finish_reason == "stop"


VERIFY_URL = "https://accounts.google.com/signin/continue?sarp=1&plt=abc"
VERIFICATION_BODY = {"error": {"code": 403, "message": "Verify your account to continue.", "status": "PERMISSION_DENIED",
                               "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                                            "reason": "VALIDATION_REQUIRED",
                                            "metadata": {"validation_url": VERIFY_URL}}]}}


def test_account_needing_verification_switches_to_another_account():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        if request.headers["authorization"] == "Bearer tok-a":
            return httpx.Response(403, json=VERIFICATION_BODY)
        return httpx.Response(200, json={"response": _gemini_payload([{"text": "ok"}])})

    source, _rotator, state = _switching_accounts()
    flagged = []

    def verify_rotator(url):
        flagged.append(url)
        state["active"] += 1
        return True

    result = _client(handler, credential_source=source, verification_rotator=verify_rotator).chat.completions.create(
        model="gemini-3-flash", messages=PARALLEL_HISTORY[:2])
    assert result.choices[0].message.content == "ok"
    assert seen == ["Bearer tok-a", "Bearer tok-b"] and flagged == [VERIFY_URL]


@pytest.mark.parametrize("stream", [False, True])
def test_verification_link_reaches_the_user_without_retrying_other_endpoints(stream):
    hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(403, json=VERIFICATION_BODY)

    client = _client(handler, verification_rotator=lambda _url: False)
    with pytest.raises(GeminiAPIError) as exc_info:
        result = client.chat.completions.create(model="gemini-3-flash", messages=PARALLEL_HISTORY[:2], stream=stream)
        list(result) if stream else None
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "antigravity_verification_required"
    assert VERIFY_URL in str(exc_info.value)
    assert len(hosts) == 1
