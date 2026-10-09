"""OpenAI-compatible facade over Google Antigravity (Cloud Code ``v1internal``).

Antigravity serves Gemini and Claude models through Google's Cloud Code
Assist backend using a Google OAuth token (see ``jettstui/antigravity_auth.py``).
The request body is a native Gemini ``generateContent`` request wrapped in an
envelope that names the Cloud Code project::

    {"project": ..., "model": ..., "request": {<gemini request>},
     "userAgent": "antigravity", "requestType": "agent", "requestId": ...}

and every response (and every SSE event) wraps the Gemini response in a
``response`` field. Translation to and from OpenAI shapes reuses
``agent/gemini_native_adapter.py``; this module only adds the envelope,
endpoint fallback, token refresh, and the Claude-on-Gemini-schema fixes.
"""

from __future__ import annotations

import copy
import logging
import re
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional

import httpx

from agent.bounded_response import read_streaming_error_body
from agent.gemini_native_adapter import (
    GeminiAPIError,
    GeminiNativeClient,
    _GeminiStreamChunk,
    _iter_sse_events,
    build_gemini_request,
    gemini_http_error,
    translate_gemini_response,
    translate_stream_event,
)

logger = logging.getLogger(__name__)

ANTIGRAVITY_HOST_MARKER = "cloudcode-pa"
SKIP_THOUGHT_SIGNATURE = "skip_thought_signature_validator"
# Claude's largest output ceiling on Antigravity; Gemini keeps the native
# adapter's 65,535 default.
CLAUDE_DEFAULT_MAX_OUTPUT_TOKENS = 64000
_CLAUDE_EFFORT_BUDGETS = {"minimal": 4096, "low": 8192, "medium": 16384, "high": 32768}
# Endpoint fallback: these statuses mean "this backend can't serve it", not
# "the request is wrong" — try the next endpoint.
_FALLBACK_STATUSES = {403, 404, 500, 502, 503, 504}

CredentialSource = Callable[..., Dict[str, Any]]


def is_antigravity_base_url(base_url: str) -> bool:
    return ANTIGRAVITY_HOST_MARKER in str(base_url or "").lower()


def is_claude_model(model: str) -> bool:
    return "claude" in (model or "").lower()


def _sanitize_tool_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name or "")[:64] or "tool"


def claude_tool_name_map(tools: Any) -> Dict[str, str]:
    """Map sanitized tool names back to the originals the agent registered."""
    mapping: Dict[str, str] = {}
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        name = (tool.get("function") or {}).get("name")
        if isinstance(name, str) and name and _sanitize_tool_name(name) != name:
            mapping.setdefault(_sanitize_tool_name(name), name)
    return mapping


def restore_tool_names(obj: Any, mapping: Dict[str, str]) -> Any:
    """Rewrite tool-call names on a translated response or stream chunk."""
    if not mapping:
        return obj
    for choice in getattr(obj, "choices", None) or []:
        holder = getattr(choice, "message", None) or getattr(choice, "delta", None)
        for call in getattr(holder, "tool_calls", None) or []:
            fn = getattr(call, "function", None)
            name = getattr(fn, "name", None)
            if name in mapping:
                fn.name = mapping[name]
    return obj


def _claude_thinking_budget(thinking_config: Optional[Dict[str, Any]]) -> int:
    if isinstance(thinking_config, dict):
        budget = thinking_config.get("thinkingBudget", thinking_config.get("thinking_budget"))
        if isinstance(budget, (int, float)) and budget > 0:
            return int(budget)
        level = str(thinking_config.get("thinkingLevel") or "").lower()
        if level in _CLAUDE_EFFORT_BUDGETS:
            return _CLAUDE_EFFORT_BUDGETS[level]
    return _CLAUDE_EFFORT_BUDGETS["high"]


def _gemini_pro_tier(model: str) -> Optional[str]:
    """``gemini-3-pro-high`` → ``high``: the tier is part of the model id."""
    match = re.match(r"^gemini-[\d.]+-pro-(low|high)$", (model or "").lower())
    return match.group(1) if match else None


def adapt_request_for_model(
    request: Dict[str, Any],
    model: str,
    *,
    thinking_config: Optional[Dict[str, Any]] = None,
    max_tokens_explicit: bool = False,
) -> Dict[str, Any]:
    """Apply the per-family tweaks Antigravity needs on a Gemini request."""
    request = copy.deepcopy(request)
    generation_config = request.setdefault("generationConfig", {})

    if not is_claude_model(model):
        tier = _gemini_pro_tier(model)
        thinking = generation_config.get("thinkingConfig")
        if tier and isinstance(thinking, dict) and thinking.get("includeThoughts") is not False:
            # The model id already selects the level; a conflicting
            # thinkingLevel is rejected.
            thinking["thinkingLevel"] = tier
        return request

    # Claude via Antigravity is validated against Anthropic's rules:
    # tool names are restricted, parameters must be an object schema,
    # and functionCall / functionResponse parts pair up by id.
    for tool in request.get("tools") or []:
        for decl in tool.get("functionDeclarations") or []:
            decl["name"] = _sanitize_tool_name(decl.get("name", ""))
            params = decl.get("parameters")
            if not isinstance(params, dict):
                params = {}
            params["type"] = "object"
            if not params.get("properties"):
                params["properties"] = {
                    "_placeholder": {"type": "boolean", "description": "Unused; pass nothing."}
                }
            decl["parameters"] = params
    if request.get("tools"):
        tool_config = request.setdefault("toolConfig", {})
        calling = tool_config.setdefault("functionCallingConfig", {})
        calling.setdefault("mode", "VALIDATED")

    pending: Dict[str, List[str]] = {}
    counter = 0
    for content in request.get("contents") or []:
        first_call_in_turn = True
        for part in content.get("parts") or []:
            call = part.get("functionCall")
            if isinstance(call, dict):
                call["name"] = _sanitize_tool_name(call.get("name", ""))
                counter += 1
                call_id = call.get("id") or f"tool-call-{counter}"
                call["id"] = call_id
                pending.setdefault(call["name"], []).append(call_id)
                # Claude signatures don't survive the Gemini schema; the first
                # call in a turn carries the validator sentinel and parallel
                # calls must carry none.
                if first_call_in_turn:
                    part["thoughtSignature"] = SKIP_THOUGHT_SIGNATURE
                    first_call_in_turn = False
                else:
                    part.pop("thoughtSignature", None)
                continue
            fn_response = part.get("functionResponse")
            if isinstance(fn_response, dict):
                fn_response["name"] = _sanitize_tool_name(fn_response.get("name", ""))
                queue = pending.get(fn_response["name"]) or []
                if queue:
                    fn_response["id"] = queue.pop(0)

    if "-thinking" in model.lower():
        include = not (isinstance(thinking_config, dict) and thinking_config.get("includeThoughts") is False)
        budget = _claude_thinking_budget(thinking_config)
        generation_config["thinkingConfig"] = (
            {"include_thoughts": True, "thinking_budget": budget} if include else {"include_thoughts": False}
        )
        if include:
            max_out = generation_config.get("maxOutputTokens") or CLAUDE_DEFAULT_MAX_OUTPUT_TOKENS
            if not max_tokens_explicit:
                max_out = CLAUDE_DEFAULT_MAX_OUTPUT_TOKENS
            # Anthropic requires max_tokens > thinking budget.
            generation_config["maxOutputTokens"] = max(int(max_out), budget + 4096)
    else:
        generation_config.pop("thinkingConfig", None)
        if not max_tokens_explicit:
            generation_config["maxOutputTokens"] = CLAUDE_DEFAULT_MAX_OUTPUT_TOKENS
    return request


def wrap_request(request: Dict[str, Any], *, model: str, project_id: str, session_id: str) -> Dict[str, Any]:
    inner = dict(request)
    inner["sessionId"] = session_id
    return {
        "project": project_id,
        "model": model,
        "request": inner,
        "userAgent": "antigravity",
        "requestType": "agent",
        "requestId": f"agent-{uuid.uuid4()}",
    }


def unwrap_response(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
        return payload["response"]
    return payload if isinstance(payload, dict) else {}


def _default_credential_source(**kwargs: Any) -> Dict[str, Any]:
    from jettstui.antigravity_auth import resolve_antigravity_runtime_credentials

    return resolve_antigravity_runtime_credentials(**kwargs)


class AntigravityClient(GeminiNativeClient):
    """OpenAI-SDK-shaped client for Antigravity's Cloud Code backend.

    The access token is short-lived; the client re-resolves credentials
    before each request (cheap: a refresh only happens near expiry) and
    force-refreshes once on HTTP 401.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: Optional[str] = None,
        project_id: str = "",
        default_headers: Optional[Dict[str, str]] = None,
        timeout: Any = None,
        http_client: Optional[httpx.Client] = None,
        credential_source: Optional[CredentialSource] = None,
        **_: Any,
    ) -> None:
        from jettstui.antigravity_auth import ANTIGRAVITY_INFERENCE_ENDPOINTS, DEFAULT_ANTIGRAVITY_BASE_URL

        super().__init__(
            api_key=api_key or "antigravity-oauth",
            base_url=base_url or DEFAULT_ANTIGRAVITY_BASE_URL,
            default_headers=default_headers,
            timeout=timeout,
            http_client=http_client,
        )
        self._credential_source = credential_source or _default_credential_source
        self._project_id = project_id
        self._fallback_token = api_key
        endpoints = [self.base_url] + [e for e in ANTIGRAVITY_INFERENCE_ENDPOINTS if e != self.base_url]
        self._endpoints = endpoints
        self._session_id = f"-{uuid.uuid4().int % 10**19}"

    # -- credentials -------------------------------------------------------

    def _refresh_credentials(self, *, force: bool = False) -> None:
        try:
            creds = self._credential_source(force_refresh=force)
        except Exception as exc:
            if self._fallback_token and self._project_id and not force:
                self.api_key = self._fallback_token
                return
            raise GeminiAPIError(
                f"Antigravity credentials unavailable: {exc}",
                code="antigravity_auth_failed",
                status_code=401,
            ) from exc
        self.api_key = str(creds.get("api_key") or "")
        self._project_id = str(creds.get("project_id") or self._project_id or "")

    def _headers(self) -> Dict[str, str]:
        from jettstui.antigravity_auth import antigravity_headers

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            **antigravity_headers(),
        }
        headers.update(self._default_headers)
        return headers

    # -- requests ----------------------------------------------------------

    def _create_chat_completion(
        self,
        *,
        model: str = "gemini-3-flash",
        messages: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        tools: Any = None,
        tool_choice: Any = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Any = None,
        extra_body: Optional[Dict[str, Any]] = None,
        timeout: Any = None,
        **_: Any,
    ) -> Any:
        thinking_config = None
        if isinstance(extra_body, dict):
            thinking_config = extra_body.get("thinking_config") or extra_body.get("thinkingConfig")
        model = (model or "").strip()
        for prefix in ("antigravity/", "google-antigravity/", "google/", "anthropic/"):
            if model.lower().startswith(prefix):
                model = model[len(prefix):]

        request = build_gemini_request(
            messages=messages or [],
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            thinking_config=thinking_config,
        )
        request = adapt_request_for_model(
            request,
            model,
            thinking_config=thinking_config if isinstance(thinking_config, dict) else None,
            max_tokens_explicit=max_tokens is not None,
        )

        name_map = claude_tool_name_map(tools) if is_claude_model(model) else {}
        self._refresh_credentials()
        if stream:
            chunks = self._stream_completion(model=model, request=request, timeout=timeout)
            if not name_map:
                return chunks
            return (restore_tool_names(chunk, name_map) for chunk in chunks)

        response = self._post_with_fallback("generateContent", model, request, timeout)
        try:
            payload = response.json()
        except ValueError as exc:
            raise GeminiAPIError(
                f"Invalid JSON from Antigravity: {exc}",
                code="gemini_invalid_json",
                status_code=response.status_code,
                response=response,
            ) from exc
        return restore_tool_names(translate_gemini_response(unwrap_response(payload), model=model), name_map)

    def _body(self, model: str, request: Dict[str, Any]) -> Dict[str, Any]:
        return wrap_request(request, model=model, project_id=self._project_id, session_id=self._session_id)

    def _post_with_fallback(self, method: str, model: str, request: Dict[str, Any], timeout: Any) -> httpx.Response:
        last_response: Optional[httpx.Response] = None
        last_exc: Optional[Exception] = None
        refreshed = False
        for endpoint in self._endpoints:
            for _attempt in range(2):
                url = f"{endpoint}/v1internal:{method}"
                try:
                    response = self._http.post(url, json=self._body(model, request), headers=self._headers(), timeout=timeout)
                except httpx.HTTPError as exc:
                    last_exc = exc
                    break
                if response.status_code == 401 and not refreshed:
                    refreshed = True
                    self._refresh_credentials(force=True)
                    continue
                if response.status_code == 200:
                    return response
                last_response = response
                break
            if last_response is not None and last_response.status_code not in _FALLBACK_STATUSES:
                break
        if last_response is not None:
            raise gemini_http_error(last_response)
        raise GeminiAPIError(f"Antigravity request failed: {last_exc}", code="gemini_stream_error") from last_exc

    def _stream_completion(self, *, model: str, request: Dict[str, Any], timeout: Any = None) -> Iterator[_GeminiStreamChunk]:
        def _generator() -> Iterator[_GeminiStreamChunk]:
            refreshed = False
            last_error: Optional[Exception] = None
            endpoints = list(self._endpoints)
            index = 0
            while index < len(endpoints):
                url = f"{endpoints[index]}/v1internal:streamGenerateContent?alt=sse"
                headers = dict(self._headers())
                headers["Accept"] = "text/event-stream"
                try:
                    with self._http.stream("POST", url, json=self._body(model, request), headers=headers, timeout=timeout) as response:
                        if response.status_code != 200:
                            body_text = read_streaming_error_body(response)
                            if response.status_code == 401 and not refreshed:
                                refreshed = True
                                self._refresh_credentials(force=True)
                                continue
                            error = gemini_http_error(response, body_text=body_text)
                            if response.status_code in _FALLBACK_STATUSES and index + 1 < len(endpoints):
                                last_error = error
                                index += 1
                                continue
                            raise error
                        tool_call_indices: Dict[str, Dict[str, Any]] = {}
                        for event in _iter_sse_events(response):
                            for chunk in translate_stream_event(unwrap_response(event), model, tool_call_indices):
                                yield chunk
                        return
                except httpx.ConnectError as exc:
                    # Nothing was streamed yet — safe to try the next endpoint.
                    last_error = exc
                    index += 1
                    continue
                except httpx.HTTPError as exc:
                    raise GeminiAPIError(
                        f"Antigravity streaming request failed: {exc}",
                        code="gemini_stream_error",
                    ) from exc
            if isinstance(last_error, GeminiAPIError):
                raise last_error
            raise GeminiAPIError(
                f"Antigravity streaming request failed: {last_error}",
                code="gemini_stream_error",
            )

        return _generator()
