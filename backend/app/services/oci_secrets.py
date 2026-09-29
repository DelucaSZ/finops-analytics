from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class OciSecretKeyError(RuntimeError):
    pass


def _cipher(key_version: str) -> Fernet:
    configured_version = settings.oci_credentials_key_version
    if key_version != configured_version:
        raise OciSecretKeyError(
            "OCI credential encryption key version is unavailable on this server"
        )
    raw = settings.oci_credentials_key.get_secret_value()
    if not raw:
        raise OciSecretKeyError("OCI credential encryption key is not configured")
    try:
        return Fernet(raw.encode())
    except (TypeError, ValueError):
        raise OciSecretKeyError("OCI credential encryption key is invalid") from None


def encrypt_secret(value: str, *, key_version: str | None = None) -> tuple[str, str]:
    version = key_version or settings.oci_credentials_key_version
    return _cipher(version).encrypt(value.encode()).decode(), version


def decrypt_secret(value: str, *, key_version: str) -> str:
    try:
        return _cipher(key_version).decrypt(value.encode()).decode()
    except InvalidToken:
        raise OciSecretKeyError(
            "OCI credential encryption key cannot decrypt the stored credential"
        ) from None
