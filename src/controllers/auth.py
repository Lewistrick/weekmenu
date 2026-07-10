"""Authentication and account management endpoints."""

from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template
from loguru import logger

from src.auth import (
    get_current_user,
    hash_password,
    login_user,
    logout_user,
    verify_password,
)
from src.catalog import seed_default_units
from src.models import Ingredient, Recipe, Shop, Tag, TagCategory, Unit, User
from src.user_settings import (
    UserSettings,
    delete_user_settings,
    load_user_settings,
    save_user_settings,
)

MIN_PASSWORD_LENGTH = 6
LANGUAGE_OPTIONS = (
    "🇬🇧 English",
    "🇳🇱 Nederlands",
    "🇫🇷 Français",
    "🇩🇪 Deutsch",
    "🇪🇸 Español",
    "🇮🇹 Italiano",
)


async def _claim_restored_data(user: User) -> None:
    """Assign restored placeholder-owned data to the first registered account.

    Database restores import catalog and recipe rows under a password-less
    placeholder user. The first real registration claims that data.

    Args:
        user: The freshly created first account.
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
    logger.info(f"Claimed restored data for first account: {user.username}")


class AuthController(Controller):
    """Register, log in/out, and manage the current account."""

    tags = ["auth"]

    @staticmethod
    def _normalize_language(value: str) -> str:
        """Return a valid language option or fall back to English."""
        normalized = value.strip()
        if normalized in LANGUAGE_OPTIONS:
            return normalized
        return "🇬🇧 English"

    @get(path="/login", summary="Login page")
    async def login_page(self, request: Request) -> Template:
        """Show the login form."""
        return Template(template_name="login.html", context={"request": request})

    @post(path="/login", summary="Log in")
    async def login(self, request: Request) -> Template | Redirect:
        """Authenticate a user and start a session."""
        form_data = await request.form()
        username = str(form_data.get("username", "")).strip()
        password = str(form_data.get("password", ""))

        user = await User.get_by_username(username) if username else None
        if user is None or not verify_password(password, user.password_hash):
            return Template(
                template_name="login.html",
                context={
                    "request": request,
                    "username": username,
                    "errors": ["Invalid username or password."],
                },
            )

        login_user(request, user)
        logger.info(f"User logged in: {user.username}")
        return Redirect(path="/")

    @get(path="/register", summary="Registration page")
    async def register_page(self, request: Request) -> Template:
        """Show the registration form."""
        return Template(template_name="register.html", context={"request": request})

    @post(path="/register", summary="Create an account")
    async def register(self, request: Request) -> Template | Redirect:
        """Create a new account, log the user in, and backfill on first signup."""
        form_data = await request.form()
        username = str(form_data.get("username", "")).strip()
        password = str(form_data.get("password", ""))
        password_confirm = str(form_data.get("password_confirm", ""))
        email = str(form_data.get("email", "")).strip()

        errors: list[str] = []
        if not username:
            errors.append("Username is required.")
        elif await User.filter(username=username, password_hash__isnull=False).exists():
            errors.append("That username is already taken.")
        if len(password) < MIN_PASSWORD_LENGTH:
            errors.append(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )
        if password != password_confirm:
            errors.append("Passwords do not match.")

        if errors:
            return Template(
                template_name="register.html",
                context={
                    "request": request,
                    "username": username,
                    "email": email,
                    "errors": errors,
                },
            )

        is_first_account = await User.filter(password_hash__isnull=False).count() == 0
        user = await User.create(
            username=username,
            email=email or "",
            password_hash=hash_password(password),
        )
        if is_first_account:
            await _claim_restored_data(user)
        await seed_default_units(user)

        login_user(request, user)
        logger.info(f"User registered: {user.username}")
        return Redirect(path="/")

    @post(path="/logout", summary="Log out")
    async def logout(self, request: Request) -> Redirect:
        """End the current session."""
        logout_user(request)
        return Redirect(path="/login")

    @get(path="/profile", summary="Account page")
    async def profile_page(self, request: Request) -> Template:
        """Show the account management page."""
        return await self._render_profile(request)

    @post(path="/profile/email", summary="Update email address")
    async def update_email(self, request: Request) -> Template | Redirect:
        """Update the current user's email address."""
        user = await get_current_user(request)
        if user is None:
            return Redirect(path="/login")
        form_data = await request.form()
        user.email = str(form_data.get("email", "")).strip()
        await user.save()
        return await self._render_profile(request, messages=["Email updated."])

    @post(path="/profile/settings", summary="Update account settings")
    async def update_settings(self, request: Request) -> Template | Redirect:
        """Update language and default week-menu servings settings."""
        user = await get_current_user(request)
        if user is None:
            return Redirect(path="/login")

        form_data = await request.form()
        language = self._normalize_language(str(form_data.get("language", "")))
        try:
            servings = int(form_data.get("servings", 2))
        except (TypeError, ValueError):
            servings = 2
        if servings < 1:
            servings = 1

        save_user_settings(user.id, UserSettings(language=language, servings=servings))
        return await self._render_profile(request, messages=["Settings updated."])

    @post(path="/profile/password", summary="Change password")
    async def change_password(self, request: Request) -> Template | Redirect:
        """Change the current user's password after verifying the old one."""
        user = await get_current_user(request)
        if user is None:
            return Redirect(path="/login")
        form_data = await request.form()
        current_password = str(form_data.get("current_password", ""))
        new_password = str(form_data.get("new_password", ""))
        new_password_confirm = str(form_data.get("new_password_confirm", ""))

        errors: list[str] = []
        if not verify_password(current_password, user.password_hash):
            errors.append("Current password is incorrect.")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            errors.append(
                f"New password must be at least {MIN_PASSWORD_LENGTH} characters."
            )
        if new_password != new_password_confirm:
            errors.append("New passwords do not match.")

        if errors:
            return await self._render_profile(request, warnings=errors)

        user.password_hash = hash_password(new_password)
        await user.save()
        logger.info(f"Password changed for user: {user.username}")
        return await self._render_profile(request, messages=["Password changed."])

    @post(path="/profile/delete", summary="Delete account")
    async def delete_account(self, request: Request) -> Redirect:
        """Delete the current account and all data owned by it."""
        user = await get_current_user(request)
        if user is not None:
            logger.info(f"Deleting account: {user.username}")
            delete_user_settings(user.id)
            await user.delete()
        logout_user(request)
        return Redirect(path="/register")

    @staticmethod
    async def _render_profile(
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Template:
        """Render the profile page with the current user and optional feedback."""
        user = await get_current_user(request)
        settings = (
            load_user_settings(user.id)
            if user is not None
            else UserSettings(language="🇬🇧 English", servings=2)
        )
        return Template(
            template_name="user-profile.html",
            context={
                "request": request,
                "current_user": user,
                "settings": settings,
                "language_options": LANGUAGE_OPTIONS,
                "messages": messages or [],
                "warnings": warnings or [],
            },
        )
