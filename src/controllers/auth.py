"""Authentication and account management endpoints."""

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Template
from loguru import logger

from src.auth import (
    get_current_user,
    hash_password,
    login_user,
    logout_user,
    verify_password,
)
from src.i18n.service import LANGUAGE_OPTIONS, t
from src.models import User
from src.url_path import path_with_base
from src.user_settings import (
    UserSettings,
    delete_user_settings,
    load_user_settings,
    save_user_settings,
)

MIN_PASSWORD_LENGTH = 6


class AuthController(Controller):
    """Log in/out and manage the current account (registration is invite-only)."""

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
                    "errors": [t("message.auth.invalid_credentials")],
                },
            )

        login_user(request, user)
        logger.info(f"User logged in: {user.username}")
        if user.must_change_password:
            return Redirect(path=path_with_base("/profile/password"))
        return Redirect(path=path_with_base("/"))

    @get(path="/register", summary="Registration page")
    async def register_page(self, request: Request) -> Template:
        """Registration is disabled; accounts are created by admins."""
        raise NotFoundException()

    @post(path="/register", summary="Create an account")
    async def register(self, request: Request) -> Template | Redirect:
        """Registration is disabled; accounts are created by admins."""
        raise NotFoundException()

    @post(path="/logout", summary="Log out")
    async def logout(self, request: Request) -> Redirect:
        """End the current session."""
        logout_user(request)
        return Redirect(path=path_with_base("/login"))

    @get(path="/profile", summary="Account page")
    async def profile_page(self, request: Request) -> Template:
        """Show the account management page."""
        return await self._render_profile(request)

    @get(path="/profile/password", summary="Change password page")
    async def password_change_page(self, request: Request) -> Template | Redirect:
        """Show the password change form (required after invite)."""
        user = await get_current_user(request)
        if user is None:
            return Redirect(path=path_with_base("/login"))
        if user.must_change_password:
            return Template(
                template_name="force-password-change.html",
                context={"request": request, "warnings": []},
            )
        return Redirect(path=path_with_base("/profile"))

    @post(path="/profile/email", summary="Update email address")
    async def update_email(self, request: Request) -> Template | Redirect:
        """Update the current user's email address."""
        user = await get_current_user(request)
        if user is None:
            return Redirect(path=path_with_base("/login"))
        form_data = await request.form()
        user.email = str(form_data.get("email", "")).strip()
        await user.save()
        return await self._render_profile(
            request, messages=[t("message.auth.email_updated")]
        )

    @post(path="/profile/settings", summary="Update account settings")
    async def update_settings(self, request: Request) -> Template | Redirect:
        """Update language and default week-menu servings settings."""
        user = await get_current_user(request)
        if user is None:
            return Redirect(path=path_with_base("/login"))

        form_data = await request.form()
        language = self._normalize_language(str(form_data.get("language", "")))
        try:
            servings = int(form_data.get("servings", 2))
        except (TypeError, ValueError):
            servings = 2
        if servings < 1:
            servings = 1

        await save_user_settings(
            user.id, UserSettings(language=language, servings=servings)
        )
        return await self._render_profile(
            request, messages=[t("message.auth.settings_updated")]
        )

    @post(path="/profile/password", summary="Change password")
    async def change_password(self, request: Request) -> Template | Redirect:
        """Change the current user's password after verifying the old one."""
        user = await get_current_user(request)
        if user is None:
            return Redirect(path=path_with_base("/login"))
        form_data = await request.form()
        current_password = str(form_data.get("current_password", ""))
        new_password = str(form_data.get("new_password", ""))
        new_password_confirm = str(form_data.get("new_password_confirm", ""))
        forced = bool(user.must_change_password)

        errors: list[str] = []
        if not forced and not verify_password(current_password, user.password_hash):
            errors.append(t("message.auth.current_password_incorrect"))
        if len(new_password) < MIN_PASSWORD_LENGTH:
            errors.append(
                t("message.auth.new_password_min_length", min=MIN_PASSWORD_LENGTH)
            )
        if new_password != new_password_confirm:
            errors.append(t("message.auth.new_passwords_no_match"))

        if errors:
            if forced:
                return Template(
                    template_name="force-password-change.html",
                    context={"request": request, "warnings": errors},
                )
            return await self._render_profile(request, warnings=errors)

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        await user.save()
        logger.info(f"Password changed for user: {user.username}")
        if forced:
            return Redirect(path=path_with_base("/"))
        return await self._render_profile(
            request, messages=[t("message.auth.password_changed")]
        )

    @post(path="/profile/delete", summary="Delete account")
    async def delete_account(self, request: Request) -> Redirect:
        """Delete the current account and all data owned by it."""
        user = await get_current_user(request)
        if user is not None:
            logger.info(f"Deleting account: {user.username}")
            delete_user_settings(user.id)
            await user.delete()
        logout_user(request)
        return Redirect(path=path_with_base("/login"))

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
            await load_user_settings(user.id)
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
