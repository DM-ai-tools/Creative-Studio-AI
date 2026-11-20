"""Creative Studio chat history, stored on the server's disk instead of only in the browser."""

from __future__ import annotations

import gzip
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services import cs_history_store as store

router = APIRouter(prefix="/cs-history", tags=["cs-history"])


class SaveChatRequest(BaseModel):
    session: dict[str, Any]
    bucket: dict[str, Any] = Field(default_factory=dict)


def _account(user) -> tuple[str, str]:
    return str(user.tenant_id), str(user.id)


@router.put("/sessions/{session_id}")
async def save_chat(session_id: str, data: SaveChatRequest, current_user=Depends(get_current_user)):
    """Save one chat. ``saved`` is false when the server already holds a newer copy of it."""
    if str(data.session.get("id") or "") != session_id:
        raise HTTPException(status_code=422, detail="The chat id does not match.")
    tenant, user = _account(current_user)
    try:
        return store.save_session(tenant, user, data.session, data.bucket)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:  # disk full, permissions, path problems: say so instead of a bare 500 trace
        raise HTTPException(status_code=500, detail=f"Chat history could not be written to disk: {exc.strerror or exc}") from exc


@router.get("/sessions")
async def list_chats(request: Request, bucket: str | None = None, current_user=Depends(get_current_user)):
    """All of this account's saved chats (optionally one list, e.g. ``brand:<id>`` or ``draft``)."""
    tenant, user = _account(current_user)
    try:
        items = store.list_sessions(tenant, user, bucket)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    body = json.dumps({"sessions": items}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Cache-Control": "no-store"}
    # Chats are text and compress well. Done here (not as app-wide middleware) so video downloads
    # served by the same app are never recompressed.
    if len(body) > 1024 and "gzip" in request.headers.get("accept-encoding", "").lower():
        body = gzip.compress(body, compresslevel=5)
        headers["Content-Encoding"] = "gzip"
    return Response(content=body, media_type="application/json", headers=headers)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(session_id: str, current_user=Depends(get_current_user)):
    tenant, user = _account(current_user)
    try:
        store.delete_session(tenant, user, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
