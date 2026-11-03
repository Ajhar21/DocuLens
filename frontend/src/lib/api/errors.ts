import type { APIResponse, ErrorDetail } from "./types";

export type ApiErrorKind =
  | "network"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "payload_too_large"
  | "validation"
  | "server"
  | "unknown";

export class ApiError extends Error {
  public readonly kind: ApiErrorKind;
  public readonly status: number;
  public readonly code: string;
  public readonly fieldErrors: Record<string, string>;
  public readonly data: unknown;

  constructor(options: {
    kind: ApiErrorKind;
    status: number;
    code: string;
    message: string;
    fieldErrors?: Record<string, string>;
    data?: unknown;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.kind = options.kind;
    this.status = options.status;
    this.code = options.code;
    this.fieldErrors = options.fieldErrors ?? {};
    this.data = options.data ?? null;
  }
}

function statusToKind(status: number): ApiErrorKind {
  if (status === 0) return "network";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 413) return "payload_too_large";
  if (status === 422 || status === 400) return "validation";
  if (status >= 500) return "server";
  return "unknown";
}

function isEnvelope(value: unknown): value is APIResponse<unknown> {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.success === "boolean" &&
    typeof candidate.message === "string"
  );
}

function extractFieldErrors(details: ErrorDetail[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const item of details) {
    if (item.field && !map[item.field]) {
      map[item.field] = item.message;
    }
  }
  return map;
}

export function normalizeApiError(status: number, body: unknown): ApiError {
  const kind = statusToKind(status);

  if (isEnvelope(body)) {
    const code = body.error?.code ?? kind;
    const details = body.error?.details ?? [];
    return new ApiError({
      kind,
      status,
      code,
      message: body.message || "Request failed",
      fieldErrors: extractFieldErrors(details),
      data: body.data,
    });
  }

  // Fallback for raw FastAPI responses or proxy gateway errors
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") {
      const code =
        status === 401 && detail.toLowerCase().includes("inactive")
          ? "account_inactive"
          : status === 401
            ? "invalid_credentials"
            : kind;
      return new ApiError({ kind, status, code, message: detail });
    }
    if (Array.isArray(detail)) {
      const fieldErrors: Record<string, string> = {};
      for (const entry of detail) {
        if (typeof entry === "object" && entry !== null) {
          const loc = (entry as { loc?: unknown[] }).loc;
          const msg = (entry as { msg?: string }).msg;
          const lastLoc = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
          if (typeof lastLoc === "string" && typeof msg === "string") {
            fieldErrors[lastLoc] = msg;
          }
        }
      }
      return new ApiError({
        kind: "validation",
        status,
        code: "validation_error",
        message: "Request validation failed",
        fieldErrors,
      });
    }
  }

  if (status === 413) {
    return new ApiError({
      kind: "payload_too_large",
      status: 413,
      code: "payload_too_large",
      message: "Uploaded payload exceeds the maximum allowed size.",
    });
  }

  return new ApiError({
    kind,
    status,
    code: kind,
    message:
      status >= 500
        ? "Server error. Please try again in a moment."
        : "The request could not be completed.",
  });
}

export function createNetworkError(message?: string): ApiError {
  return new ApiError({
    kind: "network",
    status: 0,
    code: "network_error",
    message:
      message ??
      "Unable to reach the server. Check your connection and try again.",
  });
}

