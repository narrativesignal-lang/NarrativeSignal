"""Admin flag helpers (no DB session import — safe for lightweight callers)."""

from __future__ import annotations

from app.core.config import settings
from app.models.user import User


def _admin_allowlist_sets() -> tuple[set[str], set[str]]:
    names = {x.strip().lower() for x in (settings.admin_usernames or "").split(",") if x.strip()}
    emails = {x.strip().lower() for x in (settings.admin_emails or "").split(",") if x.strip()}
    return names, emails


def user_is_admin(user: User) -> bool:
    """
    Admin flag for admin-only HTTP APIs and /auth/me.is_admin.
    Uses users.is_admin; optional ADMIN_USERNAMES / ADMIN_EMAILS env narrows who counts as admin.
    """
    if not getattr(user, "is_admin", False):
        return False
    name_set, email_set = _admin_allowlist_sets()
    if not name_set and not email_set:
        return True
    uname = (getattr(user, "username", None) or "").strip().lower()
    email = (getattr(user, "email", None) or "").strip().lower()
    if name_set and email_set:
        return uname in name_set or email in email_set
    if name_set:
        return uname in name_set
    return email in email_set
