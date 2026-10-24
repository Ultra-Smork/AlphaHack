"""Load all runtime settings from environment variables.

Local development reads .env; production uses real env vars. Nothing else in
the app reads os.environ.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)")
_UNITS = {
    "ns": 1e-9,
    "us": 1e-6,
    "µs": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}


class Database(BaseModel):
    url: str


class JWT(BaseModel):
    secret: str
    ttl: timedelta


class AI(BaseModel):
    # mock forces the deterministic offline assistant, ignoring provider creds.
    mock: bool
    base_url: str
    api_key: str
    model: str


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    http_addr: str = ":8000"

    database_url: str = "sqlite:///./alphahack.db"
    drop_on_start: bool = False

    jwt_secret: str = "dev-insecure-change-me"
    jwt_ttl: timedelta = timedelta(hours=24)

    ml_mode: Literal["mock", "http"] = "mock"
    ml_base_url: str = "http://localhost:8001"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    ai_mock: bool = True
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"

    @field_validator("jwt_ttl", mode="before")
    @classmethod
    def _parse_ttl(cls, value: object) -> object:
        if isinstance(value, timedelta):
            return value
        try:
            return parse_duration(str(value))
        except ValueError as exc:
            raise ValueError(f"config: parse JWT_TTL: {exc}") from exc

    @field_validator("ai_mock", "drop_on_start", mode="before")
    @classmethod
    def _parse_bool(cls, value: object) -> object:
        if isinstance(value, bool) or value is None:
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}

    @field_validator("ai_base_url", mode="after")
    @classmethod
    def _trim_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("ml_base_url", mode="after")
    @classmethod
    def _trim_ml_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def database(self) -> Database:
        return Database(url=self.database_url)

    @property
    def jwt(self) -> JWT:
        return JWT(secret=self.jwt_secret, ttl=self.jwt_ttl)

    @property
    def ai(self) -> AI:
        return AI(
            mock=self.ai_mock,
            base_url=self.ai_base_url,
            api_key=self.ai_api_key,
            model=self.ai_model,
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def addr(self) -> tuple[str, int]:
        """Split HTTP_ADDR (":8000" or "host:port") into a uvicorn host/port."""
        host, _, port = self.http_addr.rpartition(":")
        return (host or "0.0.0.0", int(port))


def parse_duration(text: str) -> timedelta:
    """Parse a Go-style duration such as "24h" or "1h30m"."""
    if not text:
        raise ValueError(f"invalid duration {text!r}")

    seconds = 0.0
    pos = 0
    for match in _DURATION_PART.finditer(text):
        if match.start() != pos:
            raise ValueError(f"invalid duration {text!r}")
        seconds += float(match.group(1)) * _UNITS[match.group(2)]
        pos = match.end()
    if pos != len(text):
        raise ValueError(f"invalid duration {text!r}")
    return timedelta(seconds=seconds)


def load() -> Config:
    """Read configuration. A missing .env is not an error."""
    return Config()
