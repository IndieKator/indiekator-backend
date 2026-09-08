ZONE_THRESHOLDS: list[tuple[float, float, str, str]] = [
    (0, 25, "extreme_fear", "Extreme Fear"),
    (26, 45, "fear", "Fear"),
    (46, 55, "neutral", "Neutral"),
    (56, 75, "greed", "Greed"),
    (76, 100, "extreme_greed", "Extreme Greed"),
]

ZONE_LABELS_ID: dict[str, str] = {
    "extreme_fear": "Extreme Fear",
    "fear": "Fear",
    "neutral": "Neutral",
    "greed": "Greed",
    "extreme_greed": "Extreme Greed",
}


def score_to_zone(score: float) -> tuple[str, str]:
    for low, high, key, label in ZONE_THRESHOLDS:
        if low <= score <= high:
            return key, label
    if score < 0:
        return "extreme_fear", "Extreme Fear"
    return "extreme_greed", "Extreme Greed"


def build_summary(
    zone_label: str,
    arah_momentum: int,
    normalized_trends: float,
) -> str:
    momentum_text = "di atas" if arah_momentum == 1 else "di bawah"
    trends_text = "tinggi" if normalized_trends >= 50 else "rendah"
    return (
        f"Pasar sedang {zone_label}, IHSG {momentum_text} MA 125 "
        f"dengan sentimen pencarian {trends_text}."
    )


def compute_breakdown_components(
    normalized_trends: float,
    arah_momentum: int,
    skala_emosi: float,
) -> list[dict]:
    if arah_momentum == 1:
        momentum_score = 50 + (normalized_trends / 100) * 50
        momentum_desc = "Harga IHSG di atas MA 125 — bias greed"
    else:
        momentum_score = 50 - (normalized_trends / 100) * 50
        momentum_desc = "Harga IHSG di bawah MA 125 — bias fear"

    return [
        {
            "name": "price_momentum",
            "label": "Price Momentum",
            "value": round(momentum_score, 2),
            "description": momentum_desc,
        },
        {
            "name": "public_sentiment",
            "label": "Public Sentiment",
            "value": round(normalized_trends, 2),
            "description": f"Google Trends 'ihsg' dinormalisasi: {normalized_trends:.1f}/100",
        },
    ]
