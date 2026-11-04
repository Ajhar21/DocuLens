import type { UserRole } from "@/lib/api/types";

/**
 * Mirrors backend `require_role(UserRole.REVIEWER)` where `UserRole.ADMIN`
 * always bypasses role checks in `app/core/deps.py`.
 */
export function canUploadDocuments(role: UserRole): boolean {
  return role === "reviewer" || role === "admin";
}

/**
 * Reprocessing documents (extraction / embedding stages) requires Reviewer or Admin.
 */
export function canReprocessDocuments(role: UserRole): boolean {
  return role === "reviewer" || role === "admin";
}

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  reviewer: "Reviewer",
  viewer: "Viewer",
};

