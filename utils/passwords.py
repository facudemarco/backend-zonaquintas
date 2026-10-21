"""Password hashing helpers with support for existing bcrypt hashes."""

from passlib.context import CryptContext


# New passwords use PBKDF2 so they are not limited by bcrypt's 72-byte input
# limit. Existing bcrypt hashes remain verifiable and are upgraded on login.
password_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated=["bcrypt"],
)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, bool]:
    """Return (valid, needs_rehash), keeping compatibility with old bcrypt."""
    scheme = password_context.identify(password_hash)
    if scheme == "bcrypt":
        # The old auth flow truncated UTF-8 input at bcrypt's 72-byte limit.
        legacy_password = password.encode("utf-8")[:72].decode("utf-8", "ignore")
        valid, replacement = password_context.verify_and_update(legacy_password, password_hash)
        return valid, replacement is not None
    if scheme == "pbkdf2_sha256":
        valid, replacement = password_context.verify_and_update(password, password_hash)
        return valid, replacement is not None
    return False, False
