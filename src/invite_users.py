"""Admin helpers for invite-only account creation."""

import secrets

from loguru import logger

from src.auth import hash_password
from src.catalog import seed_default_units
from src.models import Ingredient, Recipe, Shop, Tag, TagCategory, Unit, User
from src.plan_store import ensure_user_preference


def generate_temporary_password() -> str:
    """Return a strong one-time password for a newly invited user."""
    return secrets.token_urlsafe(18)


async def claim_restored_data(user: User) -> None:
    """Assign restored placeholder-owned data to an account.

    Database restores import catalog and recipe rows under a password-less
    placeholder user. The first real account can claim that data.

    Args:
        user: The account that should inherit placeholder-owned rows.
    """
    legacy_ids = (
        await User.filter(password_hash__isnull=True)
        .exclude(id=user.id)
        .values_list("id", flat=True)
    )
    if not legacy_ids:
        return

    await Recipe.filter(owner_id__in=legacy_ids).update(
        owner_id=user.id, creator_id=user.id
    )
    await Ingredient.filter(owner_id__in=legacy_ids).update(owner_id=user.id)
    await Unit.filter(owner_id__in=legacy_ids).update(owner_id=user.id)
    await TagCategory.filter(owner_id__in=legacy_ids).update(owner_id=user.id)
    await Tag.filter(owner_id__in=legacy_ids).update(owner_id=user.id)
    await Shop.filter(owner_id__in=legacy_ids).update(owner_id=user.id)
    await User.filter(id__in=legacy_ids).delete()
    logger.info(f"Claimed restored data for account: {user.username}")


async def create_invited_user(
    *,
    username: str,
    email: str = "",
    temporary_password: str | None = None,
) -> tuple[User, str]:
    """Create a user with a temporary password that must be changed.

    If a password-less placeholder user already exists with the same username
    (from a database restore), that row is activated instead of creating a
    duplicate.

    Args:
        username: Unique username for the new account.
        email: Optional email address.
        temporary_password: Password to set; generated when omitted.

    Returns:
        The created user and the plaintext temporary password.

    Raises:
        ValueError: If the username is already taken by an activated account.
    """
    password = temporary_password or generate_temporary_password()
    existing = await User.get_by_username(username)
    if existing is not None:
        if existing.password_hash is not None:
            msg = f"Username already taken: {username}"
            raise ValueError(msg)
        existing.email = email
        existing.password_hash = hash_password(password)
        existing.must_change_password = True
        await existing.save()
        user = existing
    else:
        user = await User.create(
            username=username,
            email=email,
            password_hash=hash_password(password),
            must_change_password=True,
        )
    await seed_default_units(user)
    await ensure_user_preference(user.id)
    await claim_restored_data(user)
    logger.info(f"Admin created invited user: {user.username}")
    return user, password
