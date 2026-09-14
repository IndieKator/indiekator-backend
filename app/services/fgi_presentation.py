"""Presentation helpers for the FGI read endpoints.

Turns a stored ``fgi_snapshots`` row into the zone labels, human summary, and
weighted component breakdown that the dashboard renders.
"""

from typing import Any

from app.services.fgi_engine import PRICE_WEIGHT, SEARCH_WEIGHT
from app.services.zone_builder import SENTIMENT_TO_ZONE
from app.services.zones import ZONE_LABELS_ID


def zone_for_sentiment(sentiment: str) -> tuple[str, str]:
    """Return the ``(zone_key, zone_label)`` pair for a stored sentiment label.

    Reads the label the engine already classified rather than re-deriving a zone
    from the numeric score, which is what keeps the retired ``score_to_zone``
    band gap out of the API.
    """
    try:
        zone_key = SENTIMENT_TO_ZONE[sentiment]
    except KeyError:
        raise ValueError(
            f"Unrecognised fgi_snapshots.sentiment label: {sentiment!r}"
        ) from None
    return zone_key, ZONE_LABELS_ID[zone_key]


def build_summary(
    zone_label: str,
    distance_pct: float,
    search_score: float,
) -> str:
    """Compose the Indonesian one-line market summary."""
    position = "di atas" if distance_pct >= 0 else "di bawah"
    interest = "tinggi" if search_score >= 50 else "rendah"
    return (
        f"Pasar sedang {zone_label}, IHSG {position} MA 125 "
        f"({distance_pct:+.2f}%) dengan sentimen pencarian {interest}."
    )


def build_components(
    price_score: float,
    search_score: float,
    distance_pct: float,
) -> list[dict[str, Any]]:
    """Break the index into its two weighted inputs.

    ``price_score`` and ``search_score`` are the values the engine actually
    combines, so ``value * weight`` summed across the returned components
    reproduces the stored ``fgi`` (modulo rounding).
    """
    position = "di atas" if distance_pct >= 0 else "di bawah"

    return [
        {
            "name": "price_momentum",
            "label": "Price Momentum",
            "value": round(price_score, 2),
            "weight": PRICE_WEIGHT,
            "contribution": round(price_score * PRICE_WEIGHT, 2),
            "description": (
                f"IHSG {position} MA 125 sebesar {distance_pct:+.2f}% "
                f"— skor {price_score:.1f}/100"
            ),
        },
        {
            "name": "public_sentiment",
            "label": "Public Sentiment",
            "value": round(search_score, 2),
            "weight": SEARCH_WEIGHT,
            "contribution": round(search_score * SEARCH_WEIGHT, 2),
            "description": (
                f"Minat pencarian Google Trends searah dengan momentum harga "
                f"— skor {search_score:.1f}/100"
            ),
        },
    ]
