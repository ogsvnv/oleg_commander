"""Validated application settings and optional YAML configuration."""

import os
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseModel):
    """MCP transport settings."""

    name: str = "Oleg Commander"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)


class SecurityConfig(BaseModel):
    """Default-deny settings for local and remote operations."""

    read_only: bool = True
    require_approval: bool = True
    allowed_directories: List[str] = Field(default_factory=list)
    allowed_ssh_hosts: List[str] = Field(default_factory=list)
    allowed_ssh_directories: Dict[str, List[str]] = Field(default_factory=dict)


class ExecutionConfig(BaseModel):
    """Bounds shared by SSH commands and file transfers."""

    timeout: int = Field(default=30, ge=1, le=600)
    max_output_bytes: int = Field(default=1048576, ge=1, le=10485760)


class LoggingConfig(BaseModel):
    """Audit-related settings (audit integration is still in progress)."""

    level: str = "INFO"
    audit_enabled: bool = True


class Config(BaseSettings):
    """Application settings, with environment overrides via nested __ keys."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        """Load config.yaml or OLEG_COMMANDER_CONFIG, then apply env overrides.

        A missing default config.yaml is fine. A missing explicitly selected
        config must fail to avoid silently losing security restrictions.
        """
        selected = path or os.getenv("OLEG_COMMANDER_CONFIG", "config.yaml")
        file_path = Path(selected).expanduser()
        if not file_path.exists():
            if path is not None or os.getenv("OLEG_COMMANDER_CONFIG"):
                raise FileNotFoundError(f"Config file not found: {file_path}")
            return cls()
        with file_path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        if not isinstance(data, dict):
            raise ValueError("Config YAML must contain a mapping")
        return cls(**data)
