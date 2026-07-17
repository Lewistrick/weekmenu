"""Authentication helpers: password hashing and session-based login state.

This module keeps authentication intentionally lightweight, suited to a locally
run application: passwords are hashed with bcrypt and the logged-in user id is
stored in the signed cookie session.
"""

import bcrypt
from litestar import Request

from src.models import User

SESSION_USER_KEY = "user_id"


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt hash as a UTF-8 string, safe to store in the database.
    """
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    Args:
        password: The plaintext password to verify.
        password_hash: The stored bcrypt hash, or ``None`` for accounts without
            a password set.

    Returns:
        ``True`` when the password matches the hash, ``False`` otherwise.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def login_user(request: Request, user: User) -> None:
    """Record a user as logged in for the current session."""
    request.session[SESSION_USER_KEY] = user.id


def logout_user(request: Request) -> None:
    """Clear the logged-in user from the current session."""
    request.session.pop(SESSION_USER_KEY, None)


async def get_current_user(request: Request) -> User | None:
    """Return the user for the current session, if authenticated.

    Args:
        request: The incoming request carrying the session cookie.

    Returns:
        The logged-in :class:`~src.models.User`, or ``None`` when the session
        holds no (valid) user id.
    """
    user_id = request.session.get(SESSION_USER_KEY)
    if not isinstance(user_id, int):
        return None
    return await User.get_or_none(id=user_id)


async def require_current_user(request: Request) -> User:
    """Return the logged-in user or raise when unauthenticated.

    Args:
        request: The incoming request.

    Returns:
        The authenticated user.

    Raises:
        NotAuthorizedException: If there is no authenticated user.
    """
    from litestar.exceptions import NotAuthorizedException

    user = await get_current_user(request)
    if user is None:
        msg = "Authentication required."
        raise NotAuthorizedException(msg)
    return user
