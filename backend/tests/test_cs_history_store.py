import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import get_current_user
from app.services import cs_history_store as store

TENANT = "11111111-1111-1111-1111-111111111111"
USER = "22222222-2222-2222-2222-222222222222"
OTHER = "33333333-3333-3333-3333-333333333333"


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def chat(sid="1700000000000-abc1234", updated=1000, title="PAYING FOR SHOPPERS", **extra):
    return {"id": sid, "title": title, "updatedAt": updated, "messages": [{"id": "m1", "role": "user", "content": "hi"}], **extra}


# ── saving and reading back ─────────────────────────────────────────────────


def test_a_chat_round_trips_exactly_and_survives_a_fresh_read(uploads):
    original = chat(videoPrompt="x" * 20000, phase="video")
    assert store.save_session(TENANT, USER, original, {"brandId": "b-1"}) == {"saved": True, "updatedAt": 1000.0}
    [item] = store.list_sessions(TENANT, USER)
    assert item["session"] == original and item["bucket"] == {"brandId": "b-1"}
    # the file is where the docs say, inside the uploads volume
    assert (uploads / "_private" / "cs_history" / store.account_folder_name(TENANT, USER) / f"{original['id']}.json").is_file()


def test_a_chat_path_stays_inside_the_windows_260_character_limit_in_a_deep_project_folder(uploads, monkeypatch):
    """Regression: two 36-character id folders made the real path 263 characters long inside OneDrive,
    so the final rename failed with WinError 3 'path not found' (temp file 255 chars, target 263)."""
    deep = r"C:\Users\Humruth\OneDrive - DotMappers IT Pvt Ltd\Desktop\CreativeStudio AI Code\CreativeStudio AI Code\CreativeStudio AI Code\backend\uploads"
    assert len(deep) == 142
    longest_id = "1" * 40  # the longest chat id the store accepts
    added = len(str(store._session_path(TENANT, USER, longest_id))) - len(str(uploads.resolve()))
    assert len(deep) + added <= 255, f"a {len(deep) + added}-character path would fail on Windows"
    # the layout that failed, for the record: base + \_private\cs_history\ + tenant\user\ + a real chat id
    assert len(deep) + len("\\_private\\cs_history\\") + 36 + 1 + 36 + 1 + len("1794994563486-eiold9j.json") == 263
    # and a real chat id (21 characters) has plenty of room
    real = len(str(store._session_path(TENANT, USER, "1794994563486-eiold9j"))) - len(str(uploads.resolve()))
    assert len(deep) + real <= 235


def test_each_account_gets_its_own_folder_and_a_different_one_for_every_account_pair():
    names = {store.account_folder_name(TENANT, USER), store.account_folder_name(TENANT, OTHER), store.account_folder_name(OTHER, USER)}
    assert len(names) == 3 and all(len(n) == 24 and n.isalnum() for n in names)
    assert store.account_folder_name(TENANT, USER) == store.account_folder_name(TENANT, USER)  # stable


def test_saving_again_replaces_the_chat_and_leaves_no_temporary_files(uploads):
    store.save_session(TENANT, USER, chat(updated=1000), {})
    newer = chat(updated=2000, title="Edited")
    newer["messages"].append({"id": "m2", "role": "assistant", "content": "done"})
    assert store.save_session(TENANT, USER, newer, {})["saved"] is True
    [item] = store.list_sessions(TENANT, USER)
    assert item["session"]["title"] == "Edited" and len(item["session"]["messages"]) == 2
    folder = uploads / "_private" / "cs_history" / store.account_folder_name(TENANT, USER)
    assert [p.name for p in folder.iterdir()] == [f"{newer['id']}.json"]  # no .tmp leftovers


def test_an_older_copy_never_overwrites_a_newer_one_but_the_same_time_does(uploads):
    store.save_session(TENANT, USER, chat(updated=5000, title="Newest"), {})
    stale = store.save_session(TENANT, USER, chat(updated=4000, title="Stale device"), {})
    assert stale == {"saved": False, "updatedAt": 5000.0}
    assert store.list_sessions(TENANT, USER)[0]["session"]["title"] == "Newest"
    # the browser edits a chat without changing updatedAt, so an equal time must still save
    assert store.save_session(TENANT, USER, chat(updated=5000, title="Same-time edit"), {})["saved"] is True
    assert store.list_sessions(TENANT, USER)[0]["session"]["title"] == "Same-time edit"


def test_chats_are_listed_newest_first_and_can_be_filtered_by_brand_brief_or_draft(uploads):
    store.save_session(TENANT, USER, chat("1700000000001-aaaaaaa", 1, "old"), {"brandId": "b1"})
    store.save_session(TENANT, USER, chat("1700000000002-bbbbbbb", 3, "new"), {"brandId": "b1"})
    store.save_session(TENANT, USER, chat("1700000000003-ccccccc", 2, "brief"), {"briefId": "r9"})
    store.save_session(TENANT, USER, chat("1700000000004-ddddddd", 4, "draft"), {})
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, USER)] == ["draft", "new", "brief", "old"]
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, USER, "brand:b1")] == ["new", "old"]
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, USER, "brief:r9")] == ["brief"]
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, USER, "draft")] == ["draft"]
    assert store.bucket_key({"brandId": "b1", "briefId": "r9"}) == "brand:b1"  # a brand wins, as in the browser


# ── kept until the user deletes them ────────────────────────────────────────


def test_there_is_no_limit_on_how_many_chats_a_user_keeps(uploads):
    for i in range(1105):
        store.save_session(TENANT, USER, chat(f"17000000{i:05d}-xxxxxxx", i, f"chat {i}"), {})
    assert len(store.list_sessions(TENANT, USER)) == 1105


def test_only_an_explicit_delete_removes_a_chat(uploads):
    store.save_session(TENANT, USER, chat("1700000000001-aaaaaaa", 1), {})
    store.save_session(TENANT, USER, chat("1700000000002-bbbbbbb", 2), {})
    assert store.delete_session(TENANT, USER, "1700000000001-aaaaaaa") is True
    assert [i["session"]["id"] for i in store.list_sessions(TENANT, USER)] == ["1700000000002-bbbbbbb"]
    assert store.delete_session(TENANT, USER, "1700000000001-aaaaaaa") is False  # already gone: not an error


def test_one_absurdly_large_chat_is_refused_but_ordinary_large_ones_are_fine(uploads):
    big_but_normal = chat(documentText="y" * (3 * 1024 * 1024))
    assert store.save_session(TENANT, USER, big_but_normal, {})["saved"] is True
    with pytest.raises(ValueError, match="too large"):
        store.save_session(TENANT, USER, chat("1700000000009-hugehuge", documentText="z" * (26 * 1024 * 1024)), {})


# ── safety ──────────────────────────────────────────────────────────────────


def test_accounts_cannot_see_or_overwrite_each_others_chats(uploads):
    store.save_session(TENANT, USER, chat(title="mine"), {})
    store.save_session(TENANT, OTHER, chat(title="theirs"), {})  # same chat id, different account
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, USER)] == ["mine"]
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, OTHER)] == ["theirs"]
    assert store.delete_session(TENANT, OTHER, chat()["id"]) is True
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, USER)] == ["mine"]  # unaffected


@pytest.mark.parametrize("bad_id", ["../evil", "a/b", "..", "x", "id with space", "a" * 200, "", ".hidden-start"])
def test_unsafe_chat_ids_are_rejected_before_touching_the_disk(uploads, bad_id):
    with pytest.raises(ValueError):
        store.save_session(TENANT, USER, {"id": bad_id, "messages": []}, {})
    with pytest.raises(ValueError):
        store.delete_session(TENANT, USER, bad_id)


@pytest.mark.parametrize("tenant,user", [("..", USER), (TENANT, "../x"), ("a/b", USER), ("", USER), (TENANT, "")])
def test_unsafe_account_ids_are_rejected(uploads, tenant, user):
    with pytest.raises(ValueError):
        store.list_sessions(tenant, user)
    assert not (uploads.parent / "x").exists()


def test_bucket_ids_from_the_browser_are_never_trusted(uploads):
    store.save_session(TENANT, USER, chat(), {"brandId": "../../etc", "briefId": "ok-1", "junk": "x"})
    [item] = store.list_sessions(TENANT, USER)
    assert item["bucket"] == {"briefId": "ok-1"}


def test_a_corrupt_file_is_skipped_not_fatal_and_the_other_chats_still_load(uploads):
    store.save_session(TENANT, USER, chat("1700000000001-aaaaaaa", 1, "good"), {})
    folder = uploads / "_private" / "cs_history" / store.account_folder_name(TENANT, USER)
    (folder / "1700000000002-bbbbbbb.json").write_text("{ not json", encoding="utf-8")
    (folder / "1700000000003-ccccccc.json").write_text(json.dumps({"session": "nope"}), encoding="utf-8")
    assert [i["session"]["title"] for i in store.list_sessions(TENANT, USER)] == ["good"]


def test_a_chat_without_messages_is_rejected(uploads):
    with pytest.raises(ValueError, match="messages"):
        store.save_session(TENANT, USER, {"id": "1700000000001-aaaaaaa"}, {})


# ── the API ─────────────────────────────────────────────────────────────────


def _client(uploads, user_id=USER):
    from app.api.v1 import cs_history

    app = FastAPI()
    app.include_router(cs_history.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id, tenant_id=TENANT)
    return TestClient(app)


def test_api_save_list_delete_and_the_account_comes_from_the_login(uploads):
    api = _client(uploads)
    body = {"session": chat(), "bucket": {"brandId": "b1"}}
    assert api.put(f"/api/v1/cs-history/sessions/{chat()['id']}", json=body).json() == {"saved": True, "updatedAt": 1000.0}
    listed = api.get("/api/v1/cs-history/sessions").json()["sessions"]
    assert [s["session"]["id"] for s in listed] == [chat()["id"]]
    assert api.get("/api/v1/cs-history/sessions", params={"bucket": "brand:other"}).json()["sessions"] == []
    # another login sees nothing of it
    assert _client(uploads, OTHER).get("/api/v1/cs-history/sessions").json()["sessions"] == []
    assert api.delete(f"/api/v1/cs-history/sessions/{chat()['id']}").status_code == 204
    assert api.get("/api/v1/cs-history/sessions").json()["sessions"] == []


def test_api_rejects_a_mismatched_id_and_bad_ids(uploads):
    api = _client(uploads)
    assert api.put("/api/v1/cs-history/sessions/1700000000099-other00", json={"session": chat(), "bucket": {}}).status_code == 422
    assert api.put("/api/v1/cs-history/sessions/short", json={"session": {"id": "short", "messages": []}, "bucket": {}}).status_code == 422
    assert api.delete("/api/v1/cs-history/sessions/x").status_code == 422


def test_api_compresses_big_lists_and_clients_still_read_them(uploads):
    api = _client(uploads)
    for i in range(12):
        api.put(f"/api/v1/cs-history/sessions/17000000000{i:02d}-aaaaaaa", json={"session": chat(f"17000000000{i:02d}-aaaaaaa", i, videoPrompt="word " * 4000), "bucket": {}})
    response = api.get("/api/v1/cs-history/sessions", headers={"Accept-Encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip" and len(response.json()["sessions"]) == 12
    assert "content-encoding" not in api.get("/api/v1/cs-history/sessions", headers={"Accept-Encoding": "identity"}).headers


# ── the private folder is never downloadable ────────────────────────────────


def test_the_files_route_refuses_the_private_folder_but_still_serves_normal_files(uploads, monkeypatch):
    import main

    store.save_session(TENANT, USER, chat(), {})
    (uploads / TENANT).mkdir(exist_ok=True)
    (uploads / TENANT / "pic.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(main, "upload_dir", uploads.resolve())
    client = TestClient(main.app)
    secret = f"/files/_private/cs_history/{TENANT}/{USER}/{chat()['id']}.json"
    assert client.get(secret).status_code == 404
    assert client.get("/files/_private/../_private/cs_history").status_code == 404
    assert client.get(f"/files/{TENANT}/pic.txt").status_code == 200
