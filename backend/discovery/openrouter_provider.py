"""OpenRouter adapter for superficial discovery. Importing this module does not make API requests."""

import json
import os
from decimal import Decimal

import httpx
from pydantic import ValidationError

from backend.discovery.models import DiscoveryBatch, ResearchResult, SelectionResult, UsageRecord

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"


def discovery_model() -> str:
    return os.getenv("BRIDGE_ENRICHMENT_MODEL", DEFAULT_MODEL)


def usage_from_openrouter(payload: dict, operation: str, *, searched: bool) -> UsageRecord:
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    server = usage.get("server_tool_use") or {}
    calls = server.get("web_search_requests", server.get("web_search", 0)) or 0
    if searched and not calls:
        calls = 1
    cost = usage.get("cost")
    return UsageRecord(
        operation=operation,
        response_id=payload.get("id"),
        model=payload.get("model", "unknown"),
        input_tokens=usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0,
        cached_input_tokens=details.get("cached_tokens", 0) or 0,
        output_tokens=usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0,
        web_search_calls=int(calls),
        raw_usage=usage or None,
        provider="openrouter",
        reported_cost_usd=Decimal(str(cost)) if cost is not None else None,
    )


class OpenRouterProvider:
    def __init__(self, client=None):
        token = os.getenv("OPENROUTER_API_KEY")
        if client is None and not token:
            raise RuntimeError("OPENROUTER_API_KEY is required for live discovery")
        self.client = client
        self.token = token

    def research(
        self, query: str, model: str, allowed_domains: list[str] | None, limit: int, search_context_size: str = "medium"
    ) -> ResearchResult:
        parameters: dict = {
            "max_results": max(1, min(limit, 10)),
            "max_total_results": max(1, min(limit, 10)),
            "max_uses": 2,
            "search_context_size": search_context_size if search_context_size in {"low", "medium", "high"} else "low",
        }
        if allowed_domains:
            parameters["allowed_domains"] = allowed_domains
            parameters["engine"] = "exa"
        payload = self._complete(model, [
            {"role": "user", "content": (
                "Research possible funding opportunities. Find official program pages. "
                "Do not assume calls are open or applicants eligible. "
                "Skip any page the objective lists as already recorded. "
                f"Find up to {limit} useful pages and cite each page you use. Objective: {query}"
            )},
        ], tools=[{
            "type": "openrouter:web_search",
            "parameters": parameters,
        }], max_tokens=1200)
        message = _message(payload)
        sources = cited_urls(message)
        grounded = {
            "id": payload.get("id"),
            "model": payload.get("model", model),
            "usage": payload.get("usage"),
            "output": [
                {"type": "web_search_call", "action": {"type": "search", "sources": sources}},
                {"type": "message", "content": [{"annotations": sources, "text": _message_text(message)}]},
            ],
        }
        return ResearchResult(
            response_id=payload.get("id") or "openrouter",
            model=model,
            summary=_message_text(message)[:12000],
            payload=grounded,
            usage=usage_from_openrouter(payload, "research", searched=True),
        )

    def select(
        self, query: str, observed_urls: set[str], research_summary: str, model: str, limit: int
    ) -> SelectionResult:
        schema = _strict_schema(DiscoveryBatch.model_json_schema())
        payload = self._complete(model, [
            {"role": "system", "content": (
                "Select possible funding opportunities for future investigation. Choose exact URLs only from "
                "the observed list. Prefer an official program page over a directory or homepage. "
                "Do not assert current availability or eligibility. "
                "Do not select a URL or program the objective lists as already recorded. "
                "summary, geography, and audience must be one line each and only when the research summary states them; "
                "otherwise leave them null. Every candidate needs a title and the webpage URL. "
                "Return an empty list if none are suitable."
            )},
            {"role": "user", "content": json.dumps({
                "objective": query,
                "research_summary": research_summary[:12000],
                "observed_urls": sorted(observed_urls)[:200],
                "max_candidates": limit,
            })},
        ], response_format={
            "type": "json_schema",
            "json_schema": {"name": "discovery_batch", "strict": True, "schema": schema},
        }, max_tokens=1500)
        message = _message(payload)
        parsed = _parse_batch(_message_text(message))
        return SelectionResult(
            response_id=payload.get("id") or "openrouter",
            candidates=parsed.candidates if parsed else [],
            usage=usage_from_openrouter(payload, "selection", searched=False),
            error=None if parsed else "Candidate selection returned no structured output",
        )

    def _complete(self, model: str, messages: list[dict], *, tools: list[dict] | None = None,
                  response_format: dict | None = None, max_tokens: int) -> dict:
        body: dict = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "provider": {"require_parameters": True},
        }
        if model == "nvidia/nemotron-3.5-super-vl:free":
            body["reasoning"] = {"enabled": False}
        if tools:
            body["tools"] = tools
        if response_format:
            body["response_format"] = response_format
        response = self._post(body)
        if response.status_code == 402:
            raise RuntimeError("OpenRouter returned HTTP 402 Payment Required; check account credits and spending limits.")
        if response.status_code >= 400:
            raise RuntimeError(f"OpenRouter request failed ({response.status_code}): {response.text[:300]}")
        return response.json()

    def _post(self, body: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.client is not None:
            return self.client.post(OPENROUTER_URL, headers=headers, json=body)
        with httpx.Client(timeout=90) as client:
            return client.post(OPENROUTER_URL, headers=headers, json=body)


def cited_urls(message: dict) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    notes = list(message.get("annotations") or [])
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                notes.extend(part.get("annotations") or [])
    for note in notes:
        if not isinstance(note, dict):
            continue
        citation = note.get("url_citation") if isinstance(note.get("url_citation"), dict) else note
        url = citation.get("url") if isinstance(citation, dict) else None
        if isinstance(url, str) and url not in seen:
            seen.add(url)
            title = citation.get("title") if isinstance(citation, dict) else None
            found.append({"url": url, "title": title} if isinstance(title, str) and title.strip() else {"url": url})
    return found


def _message(payload: dict) -> dict:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenRouter returned no message") from exc
    if not isinstance(message, dict):
        raise TypeError("OpenRouter returned no message")
    return message


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _parse_batch(content: str) -> DiscoveryBatch | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    if not text:
        return None
    try:
        return DiscoveryBatch.model_validate_json(text)
    except ValidationError:
        return None


def _strict_schema(schema: dict) -> dict:
    schema = {key: _strict_schema(value) if isinstance(value, dict) else
              [_strict_schema(item) if isinstance(item, dict) else item for item in value] if isinstance(value, list)
              else value for key, value in schema.items() if key != "default"}
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        schema["required"] = list(schema.get("properties", {}))
    return schema
