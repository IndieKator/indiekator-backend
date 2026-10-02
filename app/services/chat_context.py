"""Build the live market snapshot the chatbot is grounded on.

The chat model only quotes figures we hand it, so this pulls the two newest
``fgi_snapshots`` rows and renders them as a compact plain-text block. Values
come straight from the database columns (EMA 13, MA 30 = ``ma_30``, and the
Google Trends ``trends_mean``), matching what the dashboard shows.
"""

from __future__ import annotations

from typing import Any

from app.db.supabase import get_supabase

_COLUMNS = (
    "week_date, fgi, sentiment, close_price, ma_30, ema_13, trends_mean"
)

NO_DATA_CONTEXT = "No market snapshot is available right now."


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _pct(value: float, base: float | None) -> str:
    if not base:
        return "n/a"
    return f"{(value - base) / base * 100:+.2f}%"


def _fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def format_market_context(rows: list[dict[str, Any]]) -> str:
    """Render newest-first snapshot rows as the model's context block."""
    if not rows:
        return NO_DATA_CONTEXT

    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    close = float(latest["close_price"])
    ema13 = _num(latest.get("ema_13"))
    ma30 = _num(latest.get("ma_30"))
    trends = _num(latest.get("trends_mean"))

    # "CURRENT" and "PREVIOUS WEEK" are separate, explicitly labelled sections
    # so the model can't quote last week's figure as the current one.
    lines = [
        f"CURRENT WEEK ({latest['week_date']}) — use these for 'now' / 'current':",
        f"- Current IHSG close: {close:,.2f}",
        f"- Current Fear & Greed Index: {round(float(latest['fgi']))} "
        f"({latest['sentiment']})",
        f"- Current EMA 13: {_fmt(ema13)} (IHSG {_pct(close, ema13)} vs EMA 13)",
        f"- Current MA 30: {_fmt(ma30)} (IHSG {_pct(close, ma30)} vs MA 30)",
        "- Current Google Trends search interest (configured FGI mean, 0-100): "
        f"{_fmt(trends, 1)}",
    ]
    if prev is not None:
        prev_close = float(prev["close_price"])
        lines += [
            f"- Weekly change in IHSG: {_pct(close, prev_close)}",
            "",
            f"PREVIOUS WEEK ({prev['week_date']}) — only for comparisons:",
            f"- Previous IHSG close: {prev_close:,.2f}",
            f"- Previous Fear & Greed Index: {round(float(prev['fgi']))}",
        ]
    lines += [
        "",
        "Fear & Greed scale (0-100): Extreme Fear <=25, Fear <=45, "
        "Neutral <=55, Greed <=75, Extreme Greed >75.",
    ]
    return "\n".join(lines)


def fetch_market_context() -> str:
    """Query the two newest snapshots and format them; never raises on no data."""
    result = (
        get_supabase()
        .table("fgi_snapshots")
        .select(_COLUMNS)
        .order("week_date", desc=True)
        .limit(2)
        .execute()
    )
    return format_market_context(result.data or [])
