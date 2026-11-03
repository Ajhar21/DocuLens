/**
 * Token storage adapter.
 *
 * Security trade-off (XSS vs CSRF):
 * Storing the JWT in `localStorage` means any JavaScript executing on this origin
 * can read it, so a successful XSS attack could exfiltrate the session token.
 * We accept this trade-off for Day 1 because the backend issues bearer tokens in
 * the JSON body rather than `httpOnly` session cookies. Keeping all reads/writes
 * behind this module allows migrating to `httpOnly` cookies later without changing
 * any feature or component code.
 */

const TOKEN_STORAGE_KEY = "doculens.auth.token";

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignore storage quota or private-browsing failures; in-memory state still works.
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Ignore storage removal errors.
  }
}

interface JwtPayload {
  exp?: number;
  sub?: string;
  role?: string;
}

/**
 * Decodes the JWT payload (`exp` claim in epoch seconds) without external libraries.
 * Returns `null` if the token is malformed or has no numeric `exp`.
 */
export function decodeTokenExpiryMs(token: string): number | null {
  try {
    const segments = token.split(".");
    const payloadSegment = segments[1];
    if (!payloadSegment) return null;
    const base64 = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const decoded = JSON.parse(window.atob(padded)) as JwtPayload;
    if (typeof decoded.exp !== "number") return null;
    return decoded.exp * 1000;
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string, skewMs = 5_000): boolean {
  const expMs = decodeTokenExpiryMs(token);
  if (expMs === null) return false;
  return Date.now() + skewMs >= expMs;
}

