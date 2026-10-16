"""Pydantic models."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


LanguageCode = Literal["auto", "en", "ur", "roman-ur", "hi"]


# ---------- Auth (Firebase) ----------

class SyncUserRequest(BaseModel):
    """Sent by the frontend after Firebase sign-in to upsert the user row."""
    display_name: Optional[str] = Field(default=None, max_length=120)
    photo_url: Optional[str] = Field(default=None, max_length=500)


class UserOut(BaseModel):
    uid: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    photo_url: Optional[str] = None
    is_admin: bool = False


# ---------- Chat ----------

class ChatRequest(BaseModel):
    conversation_id: Optional[int] = None
    message: str = Field(..., min_length=1)
    language: LanguageCode = "auto"
    history_limit: Optional[int] = Field(default=None, ge=0, le=100)

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message must not be empty.")
        return v


class ChatResponse(BaseModel):
    conversation_id: int
    reply: str
    model: str


class ConversationSummary(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ConversationDetail(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageOut]


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title must not be empty.")
        return v


class HealthResponse(BaseModel):
    status: str
    api_key_configured: bool
    model: str
    auth_configured: bool
    version: str = "2.0.0"


ConversationDetail.model_rebuild()