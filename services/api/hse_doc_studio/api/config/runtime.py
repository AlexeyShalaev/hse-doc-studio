"""Настройки HTTP-сервера, CORS и логирования."""

from pydantic import BaseModel, Field


class HttpServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str = Field(default="0.0.0.0", description="Server bind address")  # noqa: S104
    port: int = Field(default=17240, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")
    timeout_keep_alive: int = Field(default=5, description="Keep-alive timeout in seconds")
    timeout_graceful_shutdown: int = Field(default=10, description="Graceful shutdown timeout in seconds")
    access_log: bool = Field(default=False, description="Enable uvicorn access log")
    proxy_headers: bool = Field(default=True, description="Trust proxy headers")
    forwarded_allow_ips: str = Field(default="*", description="Trusted proxy IPs")


class CorsConfig(BaseModel):
    """CORS configuration."""

    allow_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:17240",
        ],
        description="Allowed origins",
    )
    allow_credentials: bool = Field(default=True)
    allow_methods: list[str] = Field(default=["*"])
    allow_headers: list[str] = Field(default=["*"])


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    use_json: bool = Field(default=False, description="JSON format (False = console)")
