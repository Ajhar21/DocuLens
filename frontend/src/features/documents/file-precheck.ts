import type { UploadPolicy } from "@/lib/api/types";

export const FALLBACK_UPLOAD_POLICY: UploadPolicy = {
  max_upload_mb: 25,
  max_upload_bytes: 25 * 1024 * 1024,
  allowed_extensions: [".csv", ".jpeg", ".jpg", ".pdf", ".png", ".xlsx"],
  accepted_content_types: [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
    "text/csv",
  ],
};

export interface FilePrecheckResult {
  valid: boolean;
  warning: string | null;
}

export function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot <= 0 || lastDot === filename.length - 1) return "";
  return filename.slice(lastDot).toLowerCase();
}

/**
 * Performs a non-blocking client-side check of extension and byte size using the
 * server's discoverable `UploadPolicy`.
 *
 * Why advisory warnings instead of silent removal:
 * The server performs authoritative validation (including magic-byte header checks).
 * Surfacing an immediate client-side warning while still allowing submission lets
 * the user remove mistakes early OR submit and see the exact server rejection reason.
 */
export function precheckFile(
  file: File,
  policy: UploadPolicy = FALLBACK_UPLOAD_POLICY,
): FilePrecheckResult {
  const ext = getFileExtension(file.name);
  if (!ext || !policy.allowed_extensions.includes(ext)) {
    return {
      valid: false,
      warning: `Unsupported extension "${ext || "none"}". Allowed: ${policy.allowed_extensions.join(", ")}`,
    };
  }

  if (file.size === 0) {
    return {
      valid: false,
      warning: "File is empty (0 bytes) and will be rejected by the server.",
    };
  }

  if (file.size > policy.max_upload_bytes) {
    return {
      valid: false,
      warning: `Exceeds maximum size of ${policy.max_upload_mb} MB.`,
    };
  }

  return { valid: true, warning: null };
}

