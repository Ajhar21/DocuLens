import type { UserRole } from "@/lib/api/types";

/**
 * UI helper for document upload visibility (`document:upload` permission).
 * UI hints only; backend `require_permission(Permission.DOCUMENT_UPLOAD)` is the authority.
 */
export function canUploadDocuments(role: UserRole): boolean {
  return (
    role === "FINANCE_EXECUTIVE" ||
    role === "FINANCE_MANAGER" ||
    role === "SYSTEM_ADMIN" ||
    role === "reviewer" ||
    role === "admin"
  );
}

/**
 * UI helper for document reprocessing visibility (`document:upload` permission).
 * UI hints only; backend `require_permission(Permission.DOCUMENT_UPLOAD)` is the authority.
 */
export function canReprocessDocuments(role: UserRole): boolean {
  return (
    role === "FINANCE_EXECUTIVE" ||
    role === "FINANCE_MANAGER" ||
    role === "SYSTEM_ADMIN" ||
    role === "reviewer" ||
    role === "admin"
  );
}

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  reviewer: "Reviewer",
  viewer: "Viewer",
  FINANCE_EXECUTIVE: "Finance Executive",
  FINANCE_MANAGER: "Finance Manager",
  ACCOUNTS_AUDIT: "Accounts Audit",
  SYSTEM_ADMIN: "System Admin",
};

