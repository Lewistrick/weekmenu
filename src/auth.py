"""Authentication helpers: password hashing and session-based login state.

This module keeps authentication intentionally lightweight, suited to a locally
run application: passwords are hashed with bcrypt and the logged-in user id is
stored in the signed cookie session.
"""

from contextvars import ContextVar

import bcrypt
from litestar import Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException

from src.models import User

SESSION_USER_KEY = "user_id"
DEFAULT_ADMIN_USERNAME = "Erick"

_current_user: ContextVar[User | None] = ContextVar("current_user", default=None)


class _TemplateCurrentUser:
    """Jinja-friendly proxy for the request-scoped user."""

    def __bool__(self) -> bool:
        """Return whether a user is bound to the current request."""
        return get_request_user() is not None

    @property
    def is_admin(self) -> bool:
        """Return whether the request user is an admin."""
        user = get_request_user()
        return user is not None and bool(user.is_admin)


template_current_user = _TemplateCurrentUser()


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


def get_request_user() -> User | None:
    """Return the user bound to the current request context, if any."""
    return _current_user.get()


async def load_request_user(request: Request) -> User | None:
    """Resolve the session user and store it on the request context var.

    Args:
        request: The incoming request carrying the session cookie.

    Returns:
        The logged-in user, or ``None`` when unauthenticated.
    """
    user = await get_current_user(request)
    _current_user.set(user)
    return user


async def ensure_default_admin() -> None:
    """Grant admin access to the configured default admin username when present."""
    await User.filter(username=DEFAULT_ADMIN_USERNAME).update(is_admin=True)


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
    user = await get_current_user(request)
    if user is None:
        msg = "Authentication required."
        raise NotAuthorizedException(msg)
    return user


async def require_admin(request: Request) -> User:
    """Return the logged-in admin user or raise when access is forbidden.

    Args:
        request: The incoming request.

    Returns:
        The authenticated admin user.

    Raises:
        PermissionDeniedException: If the user is missing or not an admin.
    """
    user = await get_current_user(request)
    if user is None or not user.is_admin:
        msg = "Admin access required."
        raise PermissionDeniedException(msg)
    return user
