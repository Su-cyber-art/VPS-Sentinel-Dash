from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "0.2.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def origin(value: str) -> str:
    value = value.rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment
            or any(c.isspace() for c in value)):
        raise ValueError("访问地址必须是 HTTP 或 HTTPS origin，例如 http://服务器IP:8080")
    _ = parsed.port  # Validate the port as well.
    return value


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("SENTINEL_DATA", "./runtime/master")))
    public_url: str = field(default_factory=lambda: os.getenv("SENTINEL_PUBLIC_URL", ""))
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(filter(None, os.getenv("SENTINEL_CORS_ORIGINS", "").split(","))))
    cookie_secure: bool = field(default_factory=lambda: os.getenv("SENTINEL_COOKIE_SECURE", "false").lower() == "true")
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    root: Path = PROJECT_ROOT
    maintenance: bool = True

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        if self.public_url:
            self.public_url = origin(self.public_url)
        self.allowed_origins = tuple(origin(x.strip()) for x in self.allowed_origins)

    @property
    def secure_cookie(self):
        return self.cookie_secure or self.public_url.startswith("https://")

    @property
    def telegram_configured(self):
        return bool(self.telegram_token and self.telegram_chat)
