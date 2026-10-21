"""Configuration management for Oleg Commander."""
import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

class ServerConfig(BaseSettings):
    """Server configuration settings."""
    
    name: str = Field(default="Oleg Commander")
    transport: str = Field(default="stdio")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8765)

class SecurityConfig(BaseSettings):
    """Security configuration settings."""
    
    read_only: bool = Field(default=True)
    require_approval: bool = Field(default=True)
    allowed_directories: List[str] = Field(default_factory=list)
    allowed_ssh_hosts: List[str] = Field(default_factory=list)

class ExecutionConfig(BaseSettings):
    """Execution configuration settings."""
    
    timeout: int = Field(default=30)
    max_output_bytes: int = Field(default=1048576)  # 1MB

class LoggingConfig(BaseSettings):
    """Logging configuration settings."""
    
    level: str = Field(default="INFO")
    audit_enabled: bool = Field(default=True)

class Config(BaseSettings):
    """Main application configuration."""
    
    server: ServerConfig = Field(default_factory=ServerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False