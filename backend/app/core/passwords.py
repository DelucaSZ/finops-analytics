from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Argon2id; use the library's maintained memory/time cost defaults.
password_hasher = PasswordHasher()
_dummy_hash = password_hasher.hash("deepops-dummy-password-not-a-user")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        valid = password_hasher.verify(password_hash or _dummy_hash, password)
        return bool(password_hash) and valid
    except (VerificationError, InvalidHashError):
        return False
