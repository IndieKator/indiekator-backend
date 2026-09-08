from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.supabase import get_supabase
from app.schemas.sentiment import ZonePeriodResponse
from app.services.zones import ZONE_LABELS_ID

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("", response_model=list[ZonePeriodResponse])
def get_zone_periods() -> list[ZonePeriodResponse]:
    supabase = get_supabase()
    result = (
        supabase.table("zone_periods")
        .select("*")
        .order("entry_date", desc=True)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="No zone periods available. Run ingestion first.")

    return [_to_response(r) for r in rows]


def _to_response(row: dict[str, Any]) -> ZonePeriodResponse:
    zone_key = row["zone"]
    return ZonePeriodResponse(
        id=row["id"],
        zone=zone_key,
        zone_label=ZONE_LABELS_ID.get(zone_key, zone_key),
        entry_date=date.fromisoformat(row["entry_date"]),
        exit_date=date.fromisoformat(row["exit_date"]) if row.get("exit_date") else None,
        duration_days=row.get("duration_days"),
        return_pct=float(row["return_pct"]) if row.get("return_pct") is not None else None,
        is_active=row.get("exit_date") is None,
    )
