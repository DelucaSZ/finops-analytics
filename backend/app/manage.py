"""Privileged host recovery for an existing account when email is unavailable."""

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.services.authentication import issue_token, token_link
from app.services.users import lock_user_changes


def recovery_link(db: Session, email: str) -> str:
    lock_user_changes(db)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active or not user.password_set:
        raise ValueError("An active account with a password is required")
    raw, _ = issue_token(db, user, "reset")
    db.commit()
    return token_link(raw, "reset")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["password-reset"])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        print(recovery_link(db, args.email))


if __name__ == "__main__":
    main()
