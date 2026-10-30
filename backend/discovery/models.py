from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class RegistrySource(BaseModel):
    id: str
    name: str
    url: HttpUrl
    kind: Literal["directory", "official_provider", "community", "other"]
    domains: list[str]
    topics: list[str] = Field(default_factory=list)


class SourceRegistry(BaseModel):
    sources: list[RegistrySource]


class DiscoveredCandidate(BaseModel):
    title: str
    url: HttpUrl
    provider_hint: str | None
    type_hint: Literal["grant", "loan", "equity", "procurement", "competition", "other", "unknown"]
    reason_to_investigate: str
    summary: str | None = Field(default=None, max_length=400)
    geography: str | None = Field(default=None, max_length=200)
    audience: str | None = Field(default=None, max_length=200)


class DiscoveryBatch(BaseModel):
    candidates: list[DiscoveredCandidate]


class UsageRecord(BaseModel):
    operation: Literal["research", "selection"]
    response_id: str | None
    model: str
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    web_search_calls: int = Field(default=0, ge=0)
    raw_usage: dict | None = None
    provider: str = "openai"
    reported_cost_usd: Decimal | None = None


class ResearchResult(BaseModel):
    response_id: str
    model: str
    summary: str
    payload: dict
    usage: UsageRecord


class SelectionResult(BaseModel):
    response_id: str
    candidates: list[DiscoveredCandidate]
    usage: UsageRecord
    error: str | None = None
