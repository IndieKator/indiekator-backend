from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.config import Settings


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def add_job(self, *args, **kwargs) -> None:
        self.calls.append("add_job")

    def start(self) -> None:
        self.calls.append("start")

    def shutdown(self) -> None:
        self.calls.append("shutdown")


def test_cloud_run_setting_does_not_start_scheduler(monkeypatch) -> None:
    fake = FakeScheduler()
    monkeypatch.setattr(main, "scheduler", fake)
    monkeypatch.setattr(
        main, "get_settings", lambda: SimpleNamespace(enable_scheduler=False)
    )

    with TestClient(main.app):
        pass

    assert fake.calls == []


def test_scheduler_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_SCHEDULER", raising=False)
    settings = Settings(
        _env_file=None,
        sectors_api_key="test",
        supabase_url="https://test.supabase.co",
        supabase_service_role_key="test",
    )

    assert settings.enable_scheduler is False


def test_enabled_setting_starts_and_stops_scheduler(monkeypatch) -> None:
    fake = FakeScheduler()
    monkeypatch.setattr(main, "scheduler", fake)
    monkeypatch.setattr(
        main, "get_settings", lambda: SimpleNamespace(enable_scheduler=True)
    )

    with TestClient(main.app):
        assert fake.calls == ["add_job", "start"]

    assert fake.calls == ["add_job", "start", "shutdown"]
