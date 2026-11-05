import { clearToken, getToken } from "@/lib/auth/token-storage";
import { config } from "@/lib/config";
import { ApiError, createNetworkError, normalizeApiError } from "./errors";
import type { APIResponse } from "./types";

type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(
  handler: UnauthorizedHandler | null,
): void {
  onUnauthorized = handler;
}

function handleUnauthorized(): void {
  clearToken();
  onUnauthorized?.();
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  query?: Record<string, string | number | boolean | undefined>;
  json?: unknown;
  formUrlEncoded?: Record<string, string>;
  /** When false, does not attach Bearer token and does not trigger global 401 redirect. */
  auth?: boolean;
  /** When true, expects a raw response body instead of the `{success, data}` envelope. */
  rawResponse?: boolean;
  signal?: AbortSignal;
  timeoutMs?: number;
}

function buildUrl(
  path: string,
  query?: Record<string, string | number | boolean | undefined>,
): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const base = `${config.apiBaseUrl}${normalizedPath}`;
  if (!query) return base;

  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `${base}?${qs}` : base;
}

function isEnvelope<T>(payload: unknown): payload is APIResponse<T> {
  if (typeof payload !== "object" || payload === null) return false;
  const rec = payload as Record<string, unknown>;
  return typeof rec.success === "boolean" && "data" in rec;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    query,
    json,
    formUrlEncoded,
    auth = true,
    rawResponse = false,
    signal,
    timeoutMs = 15_000,
  } = options;

  const headers = new Headers({ Accept: "application/json" });

  if (auth) {
    const token = getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  let body: BodyInit | undefined;
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  } else if (formUrlEncoded !== undefined) {
    headers.set("Content-Type", "application/x-www-form-urlencoded");
    body = new URLSearchParams(formUrlEncoded).toString();
  }

  const timeoutController = new AbortController();
  const timer = window.setTimeout(() => timeoutController.abort(), timeoutMs);
  const combinedSignal = signal
    ? AbortSignal.any([signal, timeoutController.signal])
    : timeoutController.signal;

  let response: Response;
  try {
    response = await window.fetch(buildUrl(path, query), {
      method,
      headers,
      body,
      signal: combinedSignal,
    });
  } catch (err) {
    window.clearTimeout(timer);
    if (signal?.aborted) {
      throw err;
    }
    throw createNetworkError();
  } finally {
    window.clearTimeout(timer);
  }

  let parsedBody: unknown = null;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      parsedBody = await response.json();
    } catch {
      parsedBody = null;
    }
  }

  if (!response.ok) {
    const apiErr = normalizeApiError(response.status, parsedBody);
    if (response.status === 401 && auth) {
      handleUnauthorized();
    }
    throw apiErr;
  }

  if (rawResponse) {
    return parsedBody as T;
  }

  if (isEnvelope<T>(parsedBody)) {
    if (!parsedBody.success || parsedBody.data === null) {
      throw normalizeApiError(response.status, parsedBody);
    }
    return parsedBody.data;
  }

  return parsedBody as T;
}

/**
 * Stream binary file bytes (PDF, images) as a Blob using Bearer auth.
 */
export async function apiDownloadBlob(
  path: string,
  options: Omit<RequestOptions, "json" | "formUrlEncoded" | "rawResponse"> = {},
): Promise<Blob> {
  const {
    method = "GET",
    query,
    auth = true,
    signal,
    timeoutMs = 30_000,
  } = options;

  const headers = new Headers();
  if (auth) {
    const token = getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const timeoutController = new AbortController();
  const timer = window.setTimeout(() => timeoutController.abort(), timeoutMs);
  const combinedSignal = signal
    ? AbortSignal.any([signal, timeoutController.signal])
    : timeoutController.signal;

  let response: Response;
  try {
    response = await window.fetch(buildUrl(path, query), {
      method,
      headers,
      signal: combinedSignal,
    });
  } catch (err) {
    window.clearTimeout(timer);
    if (signal?.aborted) throw err;
    throw createNetworkError();
  } finally {
    window.clearTimeout(timer);
  }

  if (!response.ok) {
    let parsedBody: unknown = null;
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      try {
        parsedBody = await response.json();
      } catch {
        parsedBody = null;
      }
    }
    const apiErr = normalizeApiError(response.status, parsedBody);
    if (response.status === 401 && auth) {
      handleUnauthorized();
    }
    throw apiErr;
  }

  return response.blob();
}

export interface UploadWithProgressOptions {
  formData: FormData;
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
}

/**
 * Multipart upload with byte-level upload progress.
 *
 * Browser `fetch` does not expose upload progress events across standard browsers,
 * so this helper uses `XMLHttpRequest` inside the same client module while sharing
 * Bearer auth injection, 401 handling, and `ApiError` normalization.
 *
 * Notably, when the backend returns `422` with `error.code === "all_files_rejected"`,
 * the envelope still carries `data: BatchUploadResponse` with per-file rejection reasons.
 * We return that `BatchUploadResponse` so the UI renders every file's server reason.
 */
export function uploadWithProgress<T>(
  path: string,
  { formData, onProgress, signal }: UploadWithProgressOptions,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", buildUrl(path), true);
    xhr.setRequestHeader("Accept", "application/json");

    const token = getToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        reject(new DOMException("Upload aborted", "AbortError"));
        return;
      }
      signal.addEventListener(
        "abort",
        () => {
          xhr.abort();
        },
        { once: true },
      );
    }

    xhr.upload.onprogress = (event: ProgressEvent) => {
      if (event.lengthComputable && onProgress) {
        const pct = Math.min(100, Math.round((event.loaded / event.total) * 100));
        onProgress(pct);
      }
    };

    xhr.onerror = () => {
      reject(createNetworkError());
    };

    xhr.onabort = () => {
      reject(new DOMException("Upload aborted", "AbortError"));
    };

    xhr.onload = () => {
      let parsed: unknown = null;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        parsed = null;
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        if (isEnvelope<T>(parsed) && parsed.data !== null) {
          resolve(parsed.data);
          return;
        }
        resolve(parsed as T);
        return;
      }

      const apiErr = normalizeApiError(xhr.status, parsed);
      if (xhr.status === 401) {
        handleUnauthorized();
      }

      // 422 `all_files_rejected` carries the full BatchUploadResponse in `data`
      // so the user can see each rejected file's server-provided reason.
      if (
        apiErr instanceof ApiError &&
        apiErr.code === "all_files_rejected" &&
        apiErr.data !== null &&
        typeof apiErr.data === "object"
      ) {
        onProgress?.(100);
        resolve(apiErr.data as T);
        return;
      }

      reject(apiErr);
    };

    xhr.send(formData);
  });
}

