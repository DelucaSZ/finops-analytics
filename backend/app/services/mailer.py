import logging
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.services.authentication import issue_token, token_link
from app.services.users import lock_user_changes

logger = logging.getLogger(__name__)


def send_link(email: str, link: str, purpose: str) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = (
        "DeepOps — convite de acesso" if purpose == "invite" else "DeepOps — recuperação de senha"
    )
    duration = "24 horas" if purpose == "invite" else "30 minutos"
    message.set_content(
        f"Use este link de uso único para definir sua senha no DeepOps (validade: {duration}):\n\n"
        f"{link}\n\nSe você não esperava esta mensagem, ignore-a. Sua senha não foi alterada."
    )
    factory = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    kwargs = {"context": ssl.create_default_context()} if settings.smtp_ssl else {}
    with factory(settings.smtp_host, settings.smtp_port, timeout=10, **kwargs) as smtp:
        if not settings.smtp_ssl:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


def request_password_reset(email: str, engine) -> None:
    # Background lookup + sending keeps the public response independent of account existence.
    if not settings.smtp_host:
        return
    try:
        with Session(engine) as db:
            lock_user_changes(db)
            user = db.scalar(
                select(User).where(
                    User.email == email, User.is_active.is_(True), User.password_set.is_(True)
                )
            )
            if user is None:
                return
            raw, _ = issue_token(db, user, "reset")
            recipient = user.email
            db.commit()
        send_link(recipient, token_link(raw, "reset"), "reset")
    except Exception:
        # Never log email addresses, reset URLs, tokens or SMTP credentials.
        logger.warning("Password reset delivery failed; review SMTP availability/configuration")
