"""Conversation CRUD — scoped to the logged-in Firebase user."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import database as db
from ..models import (
    ConversationDetail,
    ConversationSummary,
    RenameConversationRequest,
)
from ..security import current_user, rate_limit

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(rate_limit)],
)


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(user: dict = Depends(current_user)) -> list[ConversationSummary]:
    rows = db.list_conversations(user["uid"])
    return [ConversationSummary(**r) for r in rows]


@router.post("", response_model=ConversationSummary, status_code=201)
async def create_conversation(user: dict = Depends(current_user)) -> ConversationSummary:
    convo = db.create_conversation(user["uid"])
    rows = db.list_conversations(user["uid"])
    match = next((c for c in rows if c["id"] == convo["id"]), None)
    if match is None:
        raise HTTPException(status_code=500, detail="Failed to create conversation.")
    return ConversationSummary(**match)


@router.get("/{cid}", response_model=ConversationDetail)
async def get_conversation(cid: int, user: dict = Depends(current_user)) -> ConversationDetail:
    convo = db.get_conversation(cid, user["uid"])
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationDetail(
        id=convo["id"],
        title=convo["title"],
        created_at=convo["created_at"],
        updated_at=convo["updated_at"],
        messages=convo["messages"],
    )


@router.patch("/{cid}", response_model=ConversationSummary)
async def rename_conversation(
    cid: int,
    payload: RenameConversationRequest,
    user: dict = Depends(current_user),
) -> ConversationSummary:
    if not db.rename_conversation(cid, user["uid"], payload.title):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    rows = db.list_conversations(user["uid"])
    match = next((c for c in rows if c["id"] == cid), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationSummary(**match)


@router.delete("/{cid}", status_code=204)
async def delete_conversation(cid: int, user: dict = Depends(current_user)) -> Response:
    if not db.delete_conversation(cid, user["uid"]):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return Response(status_code=204)


@router.delete("", status_code=204)
async def clear_all(user: dict = Depends(current_user)) -> Response:
    db.clear_all_conversations(user["uid"])
    return Response(status_code=204)