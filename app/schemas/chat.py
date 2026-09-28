from typing import Literal

from pydantic import BaseModel, Field

# Bounds keep a single request cheap for the upstream model and stop the
# endpoint being used to push arbitrarily large payloads through our key.
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 2000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    """Conversation so far, oldest first. The last message must be the user's."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)


class ChatResponse(BaseModel):
    reply: str
    model: str
