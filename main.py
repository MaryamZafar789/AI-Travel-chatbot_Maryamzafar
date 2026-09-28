

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import store
from model import generate_response
from rag import kb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("travel_chatbot")

app = FastAPI(title="Local Travel AI Chatbot API", version="1.1")


ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "https://www.example-travel-site.com",  # TODO: replace with real domain before deployment
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

RESPONSE_TIMEOUT_SECONDS = 8
_executor = ThreadPoolExecutor(max_workers=8)

MAX_MESSAGE_LENGTH = 1000
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 20
import time
from collections import defaultdict
_request_log: dict = defaultdict(list)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    language: str = "auto"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    language: str
    category: Optional[str] = None
    escalate: bool = False
    sources: list = []


class FeedbackRequest(BaseModel):
    session_id: str
    message_id: Optional[str] = None
    helpful: bool


def _rate_limit_check(key: str):
    now = time.time()
    window = _request_log[key]
    window[:] = [t for t in window if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(window) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    window.append(now)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": "prototype-template-generator",
        "vector_db": "in-memory TF-IDF (prototype)",
        "knowledge_chunks_indexed": len(kb._approved_chunks),
        "active_sessions": store.count_sessions(),
    }


@app.post("/api/session")
def create_session():
    session_id = store.create_session()
    logger.info("session created id=%s", session_id)
    return {"session_id": session_id}


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    if store.delete_session(session_id):
        return {"session_id": session_id, "deleted": True}
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    client_key = request.client.host if request.client else "unknown"
    _rate_limit_check(client_key)

    # Session must already exist -- created via POST /api/session. The
    # widget is responsible for awaiting that call before enabling input;
    # the backend's job is to refuse, not to paper over a missing session.
    if not store.session_exists(req.session_id):
        raise HTTPException(
            status_code=400,
            detail="Unknown session_id. Call POST /api/session first and wait for the response before sending messages.",
        )

    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Reject overlapping requests for the same session instead of racing
    # on shared state.
    if not store.try_acquire_pending(req.session_id):
        raise HTTPException(status_code=429, detail="A previous message is still being processed for this session.")

    try:
        state = store.get_state(req.session_id)
        future = _executor.submit(generate_response, message, state, req.language)
        try:
            result = future.result(timeout=RESPONSE_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            logger.error("generate_response timed out session=%s", req.session_id)
            raise HTTPException(status_code=504, detail="The assistant took too long to respond. Please try again.")

        store.set_state(req.session_id, result.state)
        store.append_history(req.session_id, "user", message)
        store.append_history(req.session_id, "assistant", result.reply)

        return ChatResponse(
            session_id=req.session_id,
            reply=result.reply,
            language=result.detected_language,
            category=result.detected_category,
            escalate=result.escalate,
            sources=result.used_chunks,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("chat processing failed session=%s", req.session_id)
        return ChatResponse(
            session_id=req.session_id,
            reply="Sorry, something went wrong on our side. Please try again, or contact us via WhatsApp for immediate help.",
            language=req.language if req.language != "auto" else "en",
            category=None,
            escalate=True,
            sources=[],
        )
    finally:
        store.release_pending(req.session_id)


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    if not store.session_exists(req.session_id):
        raise HTTPException(status_code=400, detail="Unknown session_id.")
    store.save_feedback(req.session_id, req.message_id, req.helpful)
    return {"received": True, "session_id": req.session_id, "helpful": req.helpful}
