import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_chat_without_session_is_rejected():
    # This is the session-race regression test: sending a chat message
    # with a session_id that was never created via POST /api/session
    # must be rejected with 400, not silently accepted (which previously
    # produced the 422 downstream error the person hit in testing).
    res = client.post("/api/chat", json={"session_id": "not-a-real-session", "message": "hello"})
    assert res.status_code == 400


def test_full_session_and_chat_flow():
    session_res = client.post("/api/session")
    assert session_res.status_code == 200
    session_id = session_res.json()["session_id"]

    chat_res = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "What documents are required for a UAE visit visa?",
        "language": "auto",
    })
    assert chat_res.status_code == 200
    body = chat_res.json()
    assert body["session_id"] == session_id
    assert "reply" in body


def test_feedback_requires_valid_session():
    res = client.post("/api/feedback", json={"session_id": "bogus", "helpful": True})
    assert res.status_code == 400


def test_feedback_persists_for_valid_session():
    session_id = client.post("/api/session").json()["session_id"]
    res = client.post("/api/feedback", json={"session_id": session_id, "helpful": True})
    assert res.status_code == 200
    assert res.json()["received"] is True


def test_delete_session():
    session_id = client.post("/api/session").json()["session_id"]
    res = client.delete(f"/api/session/{session_id}")
    assert res.status_code == 200
    # Chatting on a deleted session should now be rejected again.
    chat_res = client.post("/api/chat", json={"session_id": session_id, "message": "hi"})
    assert chat_res.status_code == 400


def test_empty_message_rejected():
    session_id = client.post("/api/session").json()["session_id"]
    res = client.post("/api/chat", json={"session_id": session_id, "message": "   "})
    assert res.status_code == 400
