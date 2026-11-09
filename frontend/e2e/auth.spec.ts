import {
  createMockJwt,
  createMockUser,
  expect,
  test,
} from "./fixtures/auth";

/**
 * E2E Suite 1: Authentication & Session Lifecycle (`auth.spec.ts`)
 *
 * Demonstrates core Playwright patterns:
 * - Page navigation (`page.goto`)
 * - User-facing locators (`getByLabel`, `getByRole`, `getByTestId`, `getByText`)
 * - Network mocking (`page.route`) for deterministic UI testing
 * - Inspecting browser `localStorage` (`page.evaluate`)
 */
test.describe("Authentication & Login Flow", () => {
  test("redirects unauthenticated user from /documents to /login", async ({
    page,
  }) => {
    await page.goto("/documents");

    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByText("Sign in to your account")).toBeVisible();
  });

  test("validates required email and password fields on empty submit", async ({
    page,
  }) => {
    await page.goto("/login");

    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.locator("#email-error")).toBeVisible();
    await expect(page.locator("#password-error")).toBeVisible();
  });

  test("renders destructive error banner when credentials are invalid (401)", async ({
    page,
  }) => {
    await page.route("**/api/auth/login", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          success: false,
          data: null,
          error: {
            code: "invalid_credentials",
            message: "Invalid email or password",
          },
        }),
      });
    });

    await page.goto("/login");
    await page.getByLabel("Email address").fill("wrong@doculens.ai");
    await page.getByLabel("Password").fill("WrongPassword123!");
    await page.getByRole("button", { name: "Sign in" }).click();

    const alert = page.getByTestId("login-error-alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Invalid credentials");
  });

  test("signs in successfully, stores JWT in localStorage, and navigates to /documents", async ({
    page,
  }) => {
    const mockToken = createMockJwt("FINANCE_MANAGER", "user-fm-1");
    const mockUser = createMockUser({
      id: "user-fm-1",
      email: "manager@doculens.ai",
      full_name: "Grace Hopper",
      role: "FINANCE_MANAGER",
    });

    await page.route("**/api/auth/login", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: mockToken,
          token_type: "bearer",
        }),
      });
    });

    await page.route("**/api/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: mockUser,
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
            allowed_extensions: [".pdf"],
            allowed_mime_types: ["application/pdf"],
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
          data: { items: [], total: 0, limit: 20, offset: 0 },
          error: null,
        }),
      });
    });

    await page.goto("/login");
    await page.getByLabel("Email address").fill("manager@doculens.ai");
    await page.getByLabel("Password").fill("CorrectHorseBatteryStaple1!");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/documents$/);
    await expect(
      page.getByRole("heading", { name: "Documents", exact: true }),
    ).toBeVisible();

    const storedToken = await page.evaluate(() =>
      window.localStorage.getItem("doculens.auth.token"),
    );
    expect(storedToken).toBe(mockToken);
  });

  test("enforces forced first-login password rotation when must_change_password is true", async ({
    page,
    loginAsRole,
  }) => {
    await loginAsRole("SYSTEM_ADMIN", { must_change_password: true });

    await page.goto("/documents");

    await expect(page).toHaveURL(/\/change-password$/);
    await expect(
      page.getByText(
        "Temporary or bootstrap credentials must be rotated on first sign-in.",
      ),
    ).toBeVisible();
  });
});
