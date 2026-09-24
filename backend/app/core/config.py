from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
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
    access_token_minutes: int = Field(480, ge=5, le=10080, alias="NUVEMIQ_ACCESS_TOKEN_MINUTES")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost"],
        alias="NUVEMIQ_CORS_ORIGINS",
    )
    session_idle_minutes: int = Field(30, ge=1, le=1440, alias="NUVEMIQ_SESSION_IDLE_MINUTES")
    cookie_secure: bool | None = Field(None, alias="NUVEMIQ_COOKIE_SECURE")
    public_url: str = Field("", alias="NUVEMIQ_PUBLIC_URL")
    mfa_required: bool = Field(False, alias="NUVEMIQ_MFA_REQUIRED")
    mfa_encryption_key: SecretStr = Field(SecretStr(""), alias="NUVEMIQ_MFA_ENCRYPTION_KEY")
    smtp_host: str = Field("", alias="NUVEMIQ_SMTP_HOST")
    smtp_port: int = Field(587, ge=1, le=65535, alias="NUVEMIQ_SMTP_PORT")
    smtp_username: str = Field("", alias="NUVEMIQ_SMTP_USERNAME")
    smtp_password: SecretStr = Field(SecretStr(""), alias="NUVEMIQ_SMTP_PASSWORD")
    smtp_from: str = Field("", alias="NUVEMIQ_SMTP_FROM")
    smtp_ssl: bool = Field(False, alias="NUVEMIQ_SMTP_SSL")

    @property
    def secure_cookies(self) -> bool:
        return (
            self.cookie_secure
            if self.cookie_secure is not None
            else self.environment == "production"
        )

    @model_validator(mode="after")
    def validate_auth_config(self) -> "Settings":
        from urllib.parse import urlsplit

        if self.environment == "production" and not self.secure_cookies:
            raise ValueError("Production requires secure cookies and HTTPS")
        if self.public_url:
            parsed = urlsplit(self.public_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("NUVEMIQ_PUBLIC_URL must be an HTTP(S) origin")
            if self.secure_cookies and parsed.scheme != "https":
                raise ValueError("Secure cookies require an HTTPS public URL")
            self.public_url = self.public_url.rstrip("/")
        if self.mfa_encryption_key.get_secret_value():
            from cryptography.fernet import Fernet

            Fernet(self.mfa_encryption_key.get_secret_value().encode())
        if self.smtp_host and (not self.public_url or not self.smtp_from):
            raise ValueError("SMTP requires NUVEMIQ_PUBLIC_URL and NUVEMIQ_SMTP_FROM")
        return self

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
