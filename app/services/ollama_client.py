"""Ollama Cloud client for generating the AI market brief.

Turns the latest ``fgi_snapshots`` figures into a short, plain-English weekly
market brief. Requests go directly to ollama.com using an API key; the model
only ever sees the numbers we hand it, so it summarises rather than invents.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_SYSTEM_PROMPT = (
    "You are a financial market analyst writing a concise weekly brief for the "
    "Indonesian stock market (IHSG / IDX Composite). Write 1-2 factual "
    "sentences in English using ONLY the figures provided. Do not invent "
    "numbers, forecasts, or advice. Keep the tone neutral and professional. "
    "Reproduce the price and percentages exactly as given. Do not use markdown "
    "or bullet points; return plain prose only."
)


def _direction_word(pct: float) -> str:
    return "up" if pct >= 0 else "down"


def _position_word(distance_pct: float) -> str:
    return "above" if distance_pct >= 0 else "below"


def build_prompt(facts: dict[str, object]) -> str:
    """Compose the user prompt from the snapshot facts.

    Values are pre-formatted so the model echoes them verbatim rather than
    reformatting numbers itself.
    """
    close = facts["close_price"]
    change_pct = float(facts["change_pct"])
    distance_pct = float(facts["distance_pct"])
    fgi = facts["fgi"]
    sentiment = facts["sentiment"]

    return (
        "Write the weekly market brief from these figures:\n"
        f"- IHSG close: {close:,.2f}\n"
        f"- Weekly change: {change_pct:+.2f}% ({_direction_word(change_pct)})\n"
        f"- Position vs EMA 20: {_position_word(distance_pct)} "
        f"({distance_pct:+.2f}%)\n"
        f"- Fear & Greed Index: {fgi} ({sentiment})\n\n"
        "Example style: \"IHSG closed at 6,441.16, down -1.53% on the week and "
        "trading above its EMA 20. The Fear & Greed Index reads 48 (Neutral).\""
    )


_CHAT_SYSTEM_PROMPT = (
    "You are IndieKator Assistant, a helpful analyst for the Indonesian stock "
    "market dashboard IndieKator (IHSG / IDX Composite Fear & Greed Index). "
    "Answer questions about IHSG, the dashboard's indicators (Fear & Greed "
    "Index, EMA 13 bands, MA 30, Google Trends search interest, trading "
    "volume), and general market concepts. When citing current figures, use "
    "ONLY the market snapshot provided below; if a figure is not provided, say "
    "you don't have it rather than guessing. Never give personalised "
    "investment advice or buy/sell recommendations; add a brief reminder that "
    "the content is informational when relevant. Reply in the user's language "
    "(Indonesian or English). Keep answers concise. Format with Markdown: "
    "**bold** for key figures, *italic* for emphasis, bullet or numbered "
    "lists for multiple points, and small tables only when comparing a few "
    "values. Do not use HTML."
)


class OllamaNotConfiguredError(RuntimeError):
    """Raised when no Ollama API key is configured."""


def _post_chat(messages: list[dict[str, str]], temperature: float) -> str:
    settings = get_settings()
    if not settings.ollama_api_key:
        raise OllamaNotConfiguredError("OLLAMA_API_KEY is not configured")

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    headers = {"Authorization": f"Bearer {settings.ollama_api_key}"}
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return (data.get("message") or {}).get("content", "").strip()


def generate_chat_reply(
    messages: list[dict[str, str]], market_context: str
) -> str:
    """Return the assistant's reply to a user/assistant conversation.

    ``messages`` holds only ``user``/``assistant`` turns from the client; the
    system prompt and live market context are always set server-side so a
    client cannot override them. Raises ``OllamaNotConfiguredError`` without a
    key and ``RuntimeError`` on an empty reply.
    """
    system = f"{_CHAT_SYSTEM_PROMPT}\n\nCurrent market snapshot:\n{market_context}"
    content = _post_chat(
        [{"role": "system", "content": system}, *messages], temperature=0.4
    )
    if not content:
        raise RuntimeError("Ollama returned an empty chat reply")
    return content


def generate_market_brief(facts: dict[str, object]) -> str:
    """Call Ollama Cloud and return the generated brief text.

    Raises ``RuntimeError`` when the key is missing or the response is empty so
    the route can fall back to a deterministic template.
    """
    settings = get_settings()
    if not settings.ollama_api_key:
        raise RuntimeError("OLLAMA_API_KEY is not configured")

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    headers = {"Authorization": f"Bearer {settings.ollama_api_key}"}
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(facts)},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = (data.get("message") or {}).get("content", "").strip()
    if not content:
        raise RuntimeError("Ollama returned an empty market brief")
    return content
