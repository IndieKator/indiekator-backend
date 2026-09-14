"""Zone presentation labels.

``ZONE_THRESHOLDS`` and ``score_to_zone`` were removed alongside the V1 index.
They had no remaining callers, and ``score_to_zone`` carried a latent defect:
its bands were closed ranges (0-25, 26-45, 46-55, 56-75, 76-100), so a
fractional score such as 25.5 matched no band and fell through to a trailing
``extreme_greed`` return. Zone derivation now reads the ``sentiment`` label that
the FGI engine already classified. See ``app.services.zone_builder``.

``build_summary`` and ``compute_breakdown_components`` were removed with the
``/api/sentiment/*`` router, their only caller. The frontend computes the
breakdown from the ``/api/fgi`` payload.
"""

ZONE_LABELS_ID: dict[str, str] = {
    "extreme_fear": "Extreme Fear",
    "fear": "Fear",
    "neutral": "Neutral",
    "greed": "Greed",
    "extreme_greed": "Extreme Greed",
}
