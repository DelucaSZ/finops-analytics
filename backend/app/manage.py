"""Privileged host recovery for an existing account when email is unavailable."""

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.services.authentication import issue_token, token_link
from app.services.mfa import reset_mfa
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
    parser.add_argument("action", choices=["password-reset", "mfa-reset"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--reason", help="Reason/ticket for audited MFA recovery")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.action == "password-reset":
            print(recovery_link(db, args.email))
        else:
            if not args.reason or not 10 <= len(args.reason.strip()) <= 500:
                parser.error("mfa-reset requires --reason (10–500 characters)")
            lock_user_changes(db)
            user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if not user or not user.is_active or not user.password_set:
                parser.error("An active account with a password is required")
            reset_mfa(db, user, None, args.reason.strip())
            db.commit()
            print("MFA reset audited. Sessions revoked; enrollment required on next login.")


if __name__ == "__main__":
    main()
