import time
from collections import defaultdict, deque
from threading import Lock

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_context import NO_DATA_CONTEXT, fetch_market_context
from app.services.ollama_client import (
    OllamaNotConfiguredError,
    generate_chat_reply,
)

router = APIRouter(prefix="/chat", tags=["chat"])

# The endpoint is public and every call spends Ollama credits, so each client
# IP gets a small sliding-window budget. In-memory only: fine for a single
# process; put a shared limiter (e.g. Redis or the gateway) in front when
# running multiple workers.
RATE_LIMIT_REQUESTS = 12
RATE_LIMIT_WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)
_hits_lock = Lock()


def _check_rate_limit(client_key: str) -> None:
    now = time.monotonic()
    with _hits_lock:
        window = _hits[client_key]
        while window and now - window[0] > RATE_LIMIT_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= RATE_LIMIT_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="Too many chat messages. Please wait a moment and try again.",
            )
        window.append(now)


def _market_context() -> str:
    # A database hiccup shouldn't block the chat; the model is told it has no
    # snapshot and will say so instead of inventing figures.
    try:
        return fetch_market_context()
    except Exception:
        return NO_DATA_CONTEXT


@router.post("", response_model=ChatResponse)
def post_chat(body: ChatRequest, request: Request) -> ChatResponse:
    """Reply to the conversation using Ollama, grounded on the latest snapshot."""
    if body.messages[-1].role != "user":
        raise HTTPException(
            status_code=422, detail="The last message must come from the user."
        )

    _check_rate_limit(request.client.host if request.client else "unknown")

    messages = [message.model_dump() for message in body.messages]
    try:
        reply = generate_chat_reply(messages, _market_context())
    except OllamaNotConfiguredError:
        raise HTTPException(
            status_code=503, detail="The assistant is not configured."
        ) from None
    except (httpx.HTTPError, RuntimeError):
        raise HTTPException(
            status_code=502,
            detail="The assistant is unavailable right now. Please try again.",
        ) from None

    return ChatResponse(reply=reply, model=get_settings().ollama_model)
