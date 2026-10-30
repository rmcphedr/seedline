"""Optional OpenAI adapter. Importing this module does not make API requests."""

import json
import os

from backend.discovery.models import DiscoveryBatch, ResearchResult, SelectionResult, UsageRecord


def usage_from_payload(payload: dict, operation: str) -> UsageRecord:
    usage = payload.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    calls = sum(
        1 for item in payload.get("output", [])
        if item.get("type") == "web_search_call" and (item.get("action") or {}).get("type") == "search"
    )
    return UsageRecord(
        operation=operation,
        response_id=payload.get("id"),
        model=payload.get("model", "unknown"),
        input_tokens=usage.get("input_tokens", 0),
        cached_input_tokens=details.get("cached_tokens", 0),
        cache_write_tokens=details.get("cache_write_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        web_search_calls=calls,
        raw_usage=usage,
    )


class OpenAIProvider:
    def __init__(self, client=None):
        if client is None:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for live discovery")
            from openai import OpenAI

            client = OpenAI()
        self.client = client

    def research(
        self, query: str, model: str, allowed_domains: list[str] | None, limit: int, search_context_size: str = "medium"
    ) -> ResearchResult:
        tool: dict = {"type": "web_search", "search_context_size": search_context_size}
        if allowed_domains:
            tool["filters"] = {"allowed_domains": allowed_domains}
        response = self.client.responses.create(
            model=model,
            tools=[tool],
            tool_choice="required",
            include=["web_search_call.action.sources"],
            max_output_tokens=1000,
            input=(
                "Research possible funding opportunities. Find official program pages; "
                "do not assume calls are open or applicants eligible. Cite the pages used. "
                "Skip any page the objective lists as already recorded. "
                f"Find up to {limit} useful pages. Objective: {query}"
            ),
        )
        payload = response.model_dump(exclude_none=True)
        return ResearchResult(
            response_id=response.id,
            model=model,
            summary=response.output_text[:12000],
            payload=payload,
            usage=usage_from_payload(payload, "research"),
        )

    def select(
        self, query: str, observed_urls: set[str], research_summary: str, model: str, limit: int
    ) -> SelectionResult:
        response = self.client.responses.parse(
            model=model,
            text_format=DiscoveryBatch,
            max_output_tokens=1000,
            input=[
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
            ],
        )
        payload = response.model_dump(exclude_none=True)
        parsed = response.output_parsed
        return SelectionResult(
            response_id=response.id,
            candidates=parsed.candidates if parsed else [],
            usage=usage_from_payload(payload, "selection"),
            error=None if parsed else "Candidate selection returned no structured output",
        )
