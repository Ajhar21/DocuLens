/**
 * UI Role-Based Access Control (RBAC) permissions mirror.
 *
 * Source: backend/app/core/permissions.py
 *
 * IMPORTANT: UI hints only; backend is the authority.
 * UI gating is a user-experience convenience only. Every API request and mutation
 * is independently and authoritatively authorized on the server.
 */

import { useMemo } from "react";
import { useAuth } from "@/features/auth/use-auth";
import type { RoleName } from "@/lib/api/types";

export const PERMISSIONS = [
  "document:upload",
  "document:view",
  "extraction:view",
  "validation:view",
  "extraction:edit",
  "correction:approve",
  "reconciliation:run",
  "reconciliation:view",
  "search:use",
  "audit:view",
  "user:manage",
  "job:view",
  "job:retry",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

const FINANCE_EXECUTIVE_PERMISSIONS: ReadonlySet<Permission> = new Set<Permission>([
  "document:upload",
  "document:view",
  "extraction:view",
  "validation:view",
  "extraction:edit",
  "reconciliation:run",
  "reconciliation:view",
  "search:use",
]);

const FINANCE_MANAGER_PERMISSIONS: ReadonlySet<Permission> = new Set<Permission>([
  ...FINANCE_EXECUTIVE_PERMISSIONS,
  "correction:approve",
  "audit:view",
]);

const ACCOUNTS_AUDIT_PERMISSIONS: ReadonlySet<Permission> = new Set<Permission>([
  "document:view",
  "extraction:view",
  "validation:view",
  "reconciliation:run",
  "reconciliation:view",
  "search:use",
  "audit:view",
]);

const SYSTEM_ADMIN_PERMISSIONS: ReadonlySet<Permission> = new Set<Permission>(PERMISSIONS);

export const ROLE_PERMISSIONS: Record<RoleName, ReadonlySet<Permission>> = {
  FINANCE_EXECUTIVE: FINANCE_EXECUTIVE_PERMISSIONS,
  FINANCE_MANAGER: FINANCE_MANAGER_PERMISSIONS,
  ACCOUNTS_AUDIT: ACCOUNTS_AUDIT_PERMISSIONS,
  SYSTEM_ADMIN: SYSTEM_ADMIN_PERMISSIONS,
};

export interface PermissionsResult {
  /** Check if the current authenticated user has the specified permission */
  can: (permission: Permission) => boolean;
  /** True when user is authenticated and active */
  isAuthenticated: boolean;
  /** The user's role if authenticated */
  role: RoleName | null;
  /** The set of active permissions for the user */
  permissions: ReadonlySet<Permission>;
}

const EMPTY_PERMISSIONS: ReadonlySet<Permission> = new Set<Permission>();

/**
 * Primary permission hook for UI gating.
 *
 * Rules:
 * - Components must NEVER branch on role names.
 * - Components must ONLY use `usePermissions().can('permission:name')`.
 */
export function usePermissions(): PermissionsResult {
  const { user, status } = useAuth();

  return useMemo(() => {
    if (status !== "authenticated" || !user || !user.is_active) {
      return {
        can: () => false,
        isAuthenticated: false,
        role: null,
        permissions: EMPTY_PERMISSIONS,
      };
    }

    const roleName = user.role as RoleName;
    const perms = ROLE_PERMISSIONS[roleName] ?? EMPTY_PERMISSIONS;

    return {
      can: (permission: Permission) => perms.has(permission),
      isAuthenticated: true,
      role: roleName,
      permissions: perms,
    };
  }, [user, status]);
}

