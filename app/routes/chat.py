"""Chat endpoint — scoped to the logged-in Firebase user."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from .. import database as db
from ..ai_service import AIServiceError, generate_reply
from ..config import get_settings
from ..models import ChatRequest, ChatResponse
from ..security import current_user, rate_limit

log = logging.getLogger("not.routes.chat")

router = APIRouter(
    prefix="/api",
    tags=["chat"],
    dependencies=[Depends(rate_limit)],
)


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: dict = Depends(current_user)) -> ChatResponse:
    settings = get_settings()

    if len(payload.message) > settings.max_message_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Message exceeds the {settings.max_message_chars}-character limit.",
        )

    uid = user["uid"]

    if payload.conversation_id is None:
        convo = db.create_conversation(uid, title=payload.message[:60])
        cid = convo["id"]
    else:
        cid = payload.conversation_id
        convo = db.get_conversation(cid, uid)
        if convo is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    if db.count_messages(cid) >= settings.max_conversation_messages:
        raise HTTPException(
            status_code=409,
            detail="This conversation has reached its message limit. Start a new chat.",
        )

    db.add_message(cid, "user", payload.message)

    history_limit = payload.history_limit or settings.max_history_messages
    history = db.get_messages(cid, limit=history_limit + 1)
    if history:
        history = [m for m in history if m["id"] != history[-1]["id"]]

    if db.count_messages(cid) <= 1:
        db.rename_conversation(cid, uid, payload.message[:60])

    try:
        reply, model = await generate_reply(
            history=history,
            user_message=payload.message,
            language=payload.language,
        )
    except AIServiceError as exc:
        log.warning("AI service error: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    db.add_message(cid, "assistant", reply)
    return ChatResponse(conversation_id=cid, reply=reply, model=model)