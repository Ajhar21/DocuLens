import { test as base, expect, type Page } from "@playwright/test";
import type { RoleName, User } from "../../src/lib/api/types";

const TOKEN_STORAGE_KEY = "doculens.auth.token";

/**
 * Creates a syntactically valid unsigned JWT whose `exp` is 1 hour in the future.
 *
 * Why we need this:
 * `src/lib/auth/token-storage.ts` decodes the middle base64 segment of the JWT
 * to check `exp` before firing `/auth/me`.
 */
export function createMockJwt(role: RoleName = "SYSTEM_ADMIN", sub = "user-1"): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString(
    "base64url",
  );
  const payload = Buffer.from(
    JSON.stringify({
      sub,
      role,
      tv: 1,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  ).toString("base64url");
  return `${header}.${payload}.mock-signature`;
}

export function createMockUser(overrides: Partial<User> = {}): User {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    email: "admin@doculens.ai",
    full_name: "Ada Lovelace",
    role: "SYSTEM_ADMIN",
    is_active: true,
    status: "active",
    must_change_password: false,
    last_login_at: "2026-11-09T12:00:00Z",
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-09T12:00:00Z",
    ...overrides,
  };
}

/**
 * Seeds browser `localStorage` with a valid JWT and mocks `/auth/me`
 * and baseline `/documents*` calls so tests can jump straight into
 * authenticated pages without repeating the UI login form every time.
 */
export async function authenticateAs(
  page: Page,
  overrides: Partial<User> = {},
): Promise<User> {
  const user = createMockUser(overrides);
  const token = createMockJwt(user.role, user.id);

  // 1. Inject the JWT into localStorage before the page scripts execute.
  await page.addInitScript(
    ([key, value]) => {
      window.localStorage.setItem(key, value);
    },
    [TOKEN_STORAGE_KEY, token] as const,
  );

  // 2. Intercept `/api/auth/me` with the DocuLens `{ success, data, error }` envelope.
  await page.route("**/api/**/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: user,
        error: null,
      }),
    });
  });

  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: user,
        error: null,
      }),
    });
  });

  // 3. Provide default empty responses for `/api/documents` & `/api/documents/upload-policy`
  // so navigating to `/documents` succeeds cleanly unless overridden by a specific test.
  await page.route("**/api/**/documents/upload-policy", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          max_file_size_bytes: 25 * 1024 * 1024,
          max_files_per_batch: 10,
          allowed_extensions: [".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".csv"],
          allowed_mime_types: [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/csv",
          ],
        },
        error: null,
      }),
    });
  });

  await page.route("**/api/documents/upload-policy", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          max_file_size_bytes: 25 * 1024 * 1024,
          max_files_per_batch: 10,
          allowed_extensions: [".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".csv"],
          allowed_mime_types: [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/csv",
          ],
        },
        error: null,
      }),
    });
  });

  await page.route("**/api/documents?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          items: [],
          total: 0,
          limit: 20,
          offset: 0,
        },
        error: null,
      }),
    });
  });

  return user;
}

interface AuthFixtures {
  loginAsRole: (role: RoleName, overrides?: Partial<User>) => Promise<User>;
}

export const test = base.extend<AuthFixtures>({
  loginAsRole: async ({ page }, use) => {
    await use((role: RoleName, overrides: Partial<User> = {}) =>
      authenticateAs(page, { role, ...overrides }),
    );
  },
});

export { expect };
