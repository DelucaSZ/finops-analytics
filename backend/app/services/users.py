from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.passwords import hash_password
from app.models.user import AuthState, User, UserRole


def lock_user_changes(db: Session) -> AuthState:
    # A write acquires a transaction lock on PostgreSQL AND SQLite. Every account
    # mutation uses this same row, so two admins cannot concurrently remove each other.
    db.execute(update(AuthState).where(AuthState.id == 1).values(id=1))
    state = db.get(AuthState, 1, populate_existing=True)
    if state is None:
        raise RuntimeError("Authentication schema has not been initialized")
    return state


def bootstrap_admin(db: Session, config: Settings) -> None:
    state = lock_user_changes(db)
    if state.bootstrap_complete:
        return
    if db.scalar(select(User.id).limit(1)) is not None:
        raise RuntimeError("Bootstrap incomplete but users already exist; inspect the database")
    if config.admin_password in {"", "change-me", "replace-this-password"}:
        raise RuntimeError("Set NUVEMIQ_ADMIN_PASSWORD before the first user migration")
    email = config.admin_email.strip().lower()
    if not email or "@" not in email or len(email) > 254:
        raise RuntimeError("Set a valid NUVEMIQ_ADMIN_EMAIL before the first user migration")
    db.add(
        User(
            name="Administrador",
            email=email,
            password_hash=hash_password(config.admin_password),
            role=UserRole.ADMIN,
        )
    )
    state.bootstrap_complete = True
    db.flush()
