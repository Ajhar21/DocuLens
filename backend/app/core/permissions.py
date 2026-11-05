"""Declarative Role-Based Access Control (RBAC) permission layer.

All route authorization checks go through ``require_permission(Permission.X)``.
Zero inline role-name checks are permitted in route handlers.
"""

from __future__ import annotations

import enum
from typing import Callable

from fastapi import Depends, status

from app.core.deps import get_current_user
from app.core.errors import AppError
from app.models.user import RoleName, User


class Permission(str, enum.Enum):
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_VIEW = "document:view"
    EXTRACTION_VIEW = "extraction:view"
    VALIDATION_VIEW = "validation:view"
    EXTRACTION_EDIT = "extraction:edit"
    CORRECTION_APPROVE = "correction:approve"
    RECONCILIATION_RUN = "reconciliation:run"
    RECONCILIATION_VIEW = "reconciliation:view"
    SEARCH_USE = "search:use"
    AUDIT_VIEW = "audit:view"
    USER_MANAGE = "user:manage"
    JOB_VIEW = "job:view"
    JOB_RETRY = "job:retry"


_FINANCE_EXECUTIVE_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.DOCUMENT_UPLOAD,
        Permission.DOCUMENT_VIEW,
        Permission.EXTRACTION_VIEW,
        Permission.VALIDATION_VIEW,
        Permission.EXTRACTION_EDIT,
        Permission.RECONCILIATION_RUN,
        Permission.RECONCILIATION_VIEW,
        Permission.SEARCH_USE,
    }
)

_FINANCE_MANAGER_PERMS: frozenset[Permission] = _FINANCE_EXECUTIVE_PERMS | frozenset(
    {
        Permission.CORRECTION_APPROVE,
        Permission.AUDIT_VIEW,
    }
)

_ACCOUNTS_AUDIT_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.DOCUMENT_VIEW,
        Permission.EXTRACTION_VIEW,
        Permission.VALIDATION_VIEW,
        Permission.RECONCILIATION_RUN,
        Permission.RECONCILIATION_VIEW,
        Permission.SEARCH_USE,
        Permission.AUDIT_VIEW,
    }
)

_SYSTEM_ADMIN_PERMS: frozenset[Permission] = frozenset(Permission)

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    RoleName.FINANCE_EXECUTIVE.value: _FINANCE_EXECUTIVE_PERMS,
    RoleName.FINANCE_MANAGER.value: _FINANCE_MANAGER_PERMS,
    RoleName.ACCOUNTS_AUDIT.value: _ACCOUNTS_AUDIT_PERMS,
    RoleName.SYSTEM_ADMIN.value: _SYSTEM_ADMIN_PERMS,
}


def has_permission(user: User, permission: Permission) -> bool:
    if not user.is_active:
        return False
    allowed = ROLE_PERMISSIONS.get(user.role_name, frozenset())
    return permission in allowed


def require_permission(permission: Permission) -> Callable[[User], User]:
    def _permission_dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, permission):
            raise AppError(
                status.HTTP_403_FORBIDDEN,
                "forbidden",
                f"Insufficient permissions: '{permission.value}' required",
            )
        return current_user

    return _permission_dependency

