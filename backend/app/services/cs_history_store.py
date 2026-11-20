"""Server-side storage for Creative Studio chat history, on the uploads volume (EBS in production).

The browser used to be the only place chats were kept (localStorage, about 5 MB), so a busy account
filled it and new chats stopped being saved. Now, like any chat product, every chat is saved on the
server and stays until the user deletes it. Each chat is one JSON file:

    <UPLOAD_DIR>/_private/cs_history/<24-char account hash>/<session_id>.json

- Inside the uploads folder, so it lives on the same persistent volume as generated media and
  survives redeploys. It is NOT public: the /files route refuses the ``_private`` folder.
- One file per chat, written atomically (temp file then rename), so a crash never leaves a half file
  and saving one chat never rewrites the others.
- tenant and user always come from the logged-in account, never from the request, so one account can
  never read or overwrite another's chats.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

PRIVATE_DIR = "_private"
# Chats are kept until the user deletes them: there is deliberately NO limit on how many a user can
# have and nothing ever expires or is cleaned up automatically. Only one absurdly large single chat
# (for example pasted binary data) is refused, so a bug cannot fill the disk with one file.
MAX_SESSION_BYTES = 25 * 1024 * 1024

# The app's chat ids are ~21 characters ("1700000000000-abc1234"). Capped at 40 so a full path stays
# well inside Windows' 260-character limit even in a deeply nested project folder.
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{5,39}$")
_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_BUCKET_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _root() -> Path:
    return Path(settings.UPLOAD_DIR).resolve() / PRIVATE_DIR / "cs_history"


def account_folder_name(tenant_id: str, user_id: str) -> str:
    """One short, fixed-length folder per account.

    Two 36-character ids as separate folders pushed full paths past Windows' 260-character limit on
    deep project folders (e.g. inside OneDrive), so saving failed with "path not found". A hash of
    both ids is 24 characters, unique per account, and cannot contain path characters.
    """
    tenant, user = str(tenant_id or ""), str(user_id or "")
    if not _PATH_SEGMENT.match(tenant) or not _PATH_SEGMENT.match(user):
        raise ValueError("Invalid account for chat history.")
    return hashlib.sha256(f"{tenant}:{user}".encode("utf-8")).hexdigest()[:24]


def _user_dir(tenant_id: str, user_id: str, *, create: bool = False) -> Path:
    path = (_root() / account_folder_name(tenant_id, user_id)).resolve()
    path.relative_to(_root())  # raises ValueError if it ever escapes the history folder
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _session_path(tenant_id: str, user_id: str, session_id: str, *, create: bool = False) -> Path:
    if not _SESSION_ID.match(str(session_id or "")):
        raise ValueError("Invalid chat id.")
    return _user_dir(tenant_id, user_id, create=create) / f"{session_id}.json"


def clean_bucket(bucket: Any) -> dict[str, str]:
    """Which brand/brief/draft list a chat belongs to. Unusable ids are dropped, never trusted."""
    out: dict[str, str] = {}
    if isinstance(bucket, dict):
        for key in ("brandId", "briefId"):
            value = str(bucket.get(key) or "").strip()
            if value and _BUCKET_ID.match(value):
                out[key] = value
    return out


def bucket_key(bucket: dict[str, str] | None) -> str:
    """Same rule the browser uses: a brand wins, then a brief, otherwise the draft list."""
    bucket = bucket or {}
    if bucket.get("brandId"):
        return f"brand:{bucket['brandId']}"
    if bucket.get("briefId"):
        return f"brief:{bucket['briefId']}"
    return "draft"


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Skipping unreadable chat history file: %s", path.name)
        return None
    return data if isinstance(data, dict) and isinstance(data.get("session"), dict) else None


def save_session(tenant_id: str, user_id: str, session: dict[str, Any], bucket: Any) -> dict[str, Any]:
    """Write one chat. Returns {"saved": bool, "updatedAt": n}; saved is False if the server has a newer copy."""
    session_id = str((session or {}).get("id") or "")
    if not isinstance(session.get("messages"), list):
        raise ValueError("A chat needs a list of messages.")
    path = _session_path(tenant_id, user_id, session_id, create=True)

    payload = json.dumps(
        {
            "bucket": clean_bucket(bucket),
            "session": session,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(payload.encode("utf-8")) > MAX_SESSION_BYTES:
        raise ValueError(f"This chat is too large to save ({MAX_SESSION_BYTES // 1_048_576} MB limit).")

    incoming = _updated_at(session)
    if path.is_file():
        existing = _read(path)
        # Another device may have saved a newer version; never overwrite newer with older.
        if existing and _updated_at(existing["session"]) > incoming:
            return {"saved": False, "updatedAt": _updated_at(existing["session"])}

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)  # atomic: readers see the old file or the new one, never half
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"saved": True, "updatedAt": incoming}


def _updated_at(session: dict[str, Any]) -> float:
    try:
        return float(session.get("updatedAt") or 0)
    except (TypeError, ValueError):
        return 0.0


def list_sessions(tenant_id: str, user_id: str, bucket: str | None = None) -> list[dict[str, Any]]:
    """Every saved chat for this account (optionally one brand/brief/draft list), newest first."""
    folder = _user_dir(tenant_id, user_id)
    if not folder.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in folder.glob("*.json"):
        data = _read(path)
        if not data:
            continue
        if bucket and bucket_key(data.get("bucket")) != bucket:
            continue
        items.append({"bucket": clean_bucket(data.get("bucket")), "session": data["session"]})
    items.sort(key=lambda item: _updated_at(item["session"]), reverse=True)
    return items


def delete_session(tenant_id: str, user_id: str, session_id: str) -> bool:
    path = _session_path(tenant_id, user_id, session_id)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
