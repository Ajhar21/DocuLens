import { describe, expect, it } from "vitest";
import { PERMISSIONS, ROLE_PERMISSIONS } from "../permissions";
import type { RoleName } from "../api/types";

describe("permissions configuration", () => {
  const canonicalRoles: RoleName[] = [
    "FINANCE_EXECUTIVE",
    "FINANCE_MANAGER",
    "ACCOUNTS_AUDIT",
    "SYSTEM_ADMIN",
  ];

  it("defines all canonical roles in the permissions map", () => {
    for (const role of canonicalRoles) {
      expect(ROLE_PERMISSIONS[role]).toBeDefined();
      expect(ROLE_PERMISSIONS[role].size).toBeGreaterThan(0);
    }
  });

  it("SYSTEM_ADMIN has every declared permission", () => {
    const adminPerms = ROLE_PERMISSIONS.SYSTEM_ADMIN;
    for (const perm of PERMISSIONS) {
      expect(adminPerms.has(perm)).toBe(true);
    }
  });

  it("all permissions in role maps are recognized in PERMISSIONS list", () => {
    const declaredSet = new Set<string>(PERMISSIONS);
    for (const [role, perms] of Object.entries(ROLE_PERMISSIONS)) {
      for (const p of perms) {
        expect(
          declaredSet.has(p),
          `Role ${role} contains unknown permission '${p}'`,
        ).toBe(true);
      }
    }
  });

  it("enforces specific RBAC invariants", () => {
    // Executive can edit extractions, cannot approve corrections
    expect(ROLE_PERMISSIONS.FINANCE_EXECUTIVE.has("extraction:edit")).toBe(true);
    expect(ROLE_PERMISSIONS.FINANCE_EXECUTIVE.has("correction:approve")).toBe(false);

    // Manager can approve corrections and edit extractions
    expect(ROLE_PERMISSIONS.FINANCE_MANAGER.has("extraction:edit")).toBe(true);
    expect(ROLE_PERMISSIONS.FINANCE_MANAGER.has("correction:approve")).toBe(true);

    // Auditor cannot edit extractions or approve corrections
    expect(ROLE_PERMISSIONS.ACCOUNTS_AUDIT.has("extraction:edit")).toBe(false);
    expect(ROLE_PERMISSIONS.ACCOUNTS_AUDIT.has("correction:approve")).toBe(false);

    // Auditor can view audit logs and run reconciliations
    expect(ROLE_PERMISSIONS.ACCOUNTS_AUDIT.has("audit:view")).toBe(true);
    expect(ROLE_PERMISSIONS.ACCOUNTS_AUDIT.has("reconciliation:run")).toBe(true);
  });
});
