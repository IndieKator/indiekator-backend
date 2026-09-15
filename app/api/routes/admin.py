from datetime import datetime

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.db.supabase import get_supabase
from app.schemas.core import HealthResponse, IngestResponse
from app.services.ingestion import run_ingestion

router = APIRouter(tags=["admin"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    supabase = get_supabase()
    result = (
        supabase.table("ingestion_runs")
        .select("finished_at, status")
        .eq("status", "success")
        .order("finished_at", desc=True)
        .limit(1)
        .execute()
    )
    last_ingestion = None
    if result.data:
        raw = result.data[0].get("finished_at")
        if raw:
            last_ingestion = datetime.fromisoformat(raw.replace("Z", "+00:00"))

    return HealthResponse(status="ok", last_ingestion=last_ingestion)


@router.post("/admin/ingest", response_model=IngestResponse)
def trigger_ingest(x_admin_secret: str = Header(...)) -> IngestResponse:
    settings = get_settings()
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    try:
        result = run_ingestion()
        return IngestResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
