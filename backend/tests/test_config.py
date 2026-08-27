from backend.app.config import Settings


def test_settings_uses_vietnam_timezone_by_default(monkeypatch):
    monkeypatch.delenv("APP_TIMEZONE", raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_timezone == "Asia/Ho_Chi_Minh"


def test_settings_reads_environment_override(monkeypatch):
    monkeypatch.setenv("SIMULATOR_LOCATION_COUNT", "12000")
    monkeypatch.setenv("SIMULATOR_INTERNAL_URL", "http://simulator.internal:9090")

    settings = Settings(_env_file=None)

    assert settings.simulator_location_count == 12000
    assert settings.simulator_internal_url == "http://simulator.internal:9090"


def test_settings_uses_local_admin_ui_origin_by_default(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)

    settings = Settings(_env_file=None)

    assert settings.frontend_origin == "http://localhost:3000"
