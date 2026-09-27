from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, chat, fgi, trading_summary, zones
from app.config import get_settings
from app.services.ingestion import run_ingestion

scheduler = BackgroundScheduler()


def _scheduled_ingest() -> None:
    try:
        run_ingestion()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        _scheduled_ingest,
        CronTrigger(hour=7, minute=0, timezone="Asia/Jakarta"),
        id="daily_ingest",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="IndieKator API",
        description="IHSG Fear & Greed Index",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(admin.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(fgi.router, prefix="/api")
    app.include_router(trading_summary.router, prefix="/api")
    app.include_router(zones.router, prefix="/api")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
