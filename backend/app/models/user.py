import uuid
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator', 'viewer')", name="ck_users_role"),
        CheckConstraint("token_version >= 1", name="ck_users_token_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1)


class AuthState(Base):
    """Singleton persists bootstrap state and serializes administrative account changes."""

    __tablename__ = "auth_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_auth_state_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bootstrap_complete: Mapped[bool] = mapped_column(Boolean, default=False)
