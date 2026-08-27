from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_timezone: str = "Asia/Ho_Chi_Minh"
    frontend_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+asyncpg://memorial:memorial@localhost:5432/memorial"

    mqtt_host: str = "localhost"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str = "memorial"
    mqtt_password: SecretStr = SecretStr("change-me")

    jwt_secret: SecretStr = SecretStr("change-me")
    jwt_expire_minutes: int = Field(default=480, gt=0)
    admin_password: SecretStr = SecretStr("change-me")
    staff_password: SecretStr = SecretStr("change-me")
    tech_password: SecretStr = SecretStr("change-me")

    simulator_admin_enabled: bool = True
    simulator_internal_url: str = "http://gateway-sim:8081"
    simulator_location_count: int = Field(default=1200, gt=0)
    simulator_zones: str = "A,B,C,D"
    simulator_locations_per_zone: int = Field(default=300, gt=0)
    simulator_controller_capacity: int = Field(default=64, gt=0)

    device_heartbeat_seconds: int = Field(default=5, gt=0)
    device_offline_after_seconds: int = Field(default=15, gt=0)
    command_ack_timeout_seconds: int = Field(default=5, gt=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
