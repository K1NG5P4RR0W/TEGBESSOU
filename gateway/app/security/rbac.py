"""Hiérarchie des rôles (RBAC, §13.3)."""

ROLE_ORDER = {"viewer": 0, "analyst": 1, "lead": 2, "admin": 3}


def role_at_least(user_role: str, required: str) -> bool:
    return ROLE_ORDER.get(user_role, -1) >= ROLE_ORDER[required]
