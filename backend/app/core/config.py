from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field("development", alias="NUVEMIQ_ENVIRONMENT")
    database_url: str = Field("sqlite:///./nuvemiq.db", alias="DATABASE_URL")
    secret_key: str = Field(
        "development-only-change-me-at-least-32-bytes", alias="NUVEMIQ_SECRET_KEY"
    )
    admin_email: str = Field("admin@nuvemiq.local", alias="NUVEMIQ_ADMIN_EMAIL")
    admin_password: str = Field("change-me", alias="NUVEMIQ_ADMIN_PASSWORD")
    access_token_minutes: int = Field(480, alias="NUVEMIQ_ACCESS_TOKEN_MINUTES")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost"],
        alias="NUVEMIQ_CORS_ORIGINS",
    )
    worker_poll_seconds: int = Field(5, alias="NUVEMIQ_WORKER_POLL_SECONDS")
    demo_mode: bool = Field(False, alias="NUVEMIQ_DEMO_MODE")
    aws_default_region: str = Field("sa-east-1", alias="AWS_DEFAULT_REGION")
    aws_role_session_name: str = Field("nuvemiq-collector", alias="AWS_ROLE_SESSION_NAME")
    ai_provider: str = Field("disabled", alias="NUVEMIQ_AI_PROVIDER")
    bedrock_region: str = Field("us-east-1", alias="NUVEMIQ_BEDROCK_REGION")
    bedrock_model_id: str = Field("", alias="NUVEMIQ_BEDROCK_MODEL_ID")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
