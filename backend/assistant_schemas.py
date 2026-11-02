"""Local demo assistant request and response contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StartConversation(BaseModel):
    opportunity_id: UUID | None = None
    restart: bool = False


class SendMessage(BaseModel):
    request_id: UUID
    content: str = Field(min_length=1, max_length=4000)


class SuggestionDecision(BaseModel):
    id: UUID
    action: Literal["accept", "reject"]
    value: object | None = None


class ConfirmSuggestions(BaseModel):
    decisions: list[SuggestionDecision] = Field(min_length=1, max_length=30)


class MessageRead(BaseModel):
    id: UUID
    role: Literal["assistant", "user"]
    content: str
    target_field: str | None
    created_at: datetime


class SuggestionRead(BaseModel):
    id: UUID
    field: str
    resource: str
    value: object
    base_value: object | None
    confidence: Literal["high", "medium", "low"]
    source_text: str
    status: Literal["pending", "accepted", "rejected"]


class ConversationRead(BaseModel):
    id: UUID
    mode: Literal["mock", "live"]
    opportunity_id: UUID | None
    opportunity_title: str | None
    messages: list[MessageRead]
    suggestions: list[SuggestionRead]
    provenance: dict[str, str]
    completion_percent: int
