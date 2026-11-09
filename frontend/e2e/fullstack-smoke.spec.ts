import { expect, test } from "@playwright/test";
import {
  E2E_ADMIN_EMAIL,
  E2E_ADMIN_NAME,
  E2E_ADMIN_PASSWORD,
} from "./global-setup";

/**
 * E2E Suite 3: Full-Stack Live Backend Smoke Tests (`fullstack-smoke.spec.ts`)
 *
 * Unlike `auth.spec.ts` and `rbac-navigation.spec.ts` (which use `page.route` network mocks),
 * this test makes ZERO mocks. Every request flows through:
 *   Chromium Browser -> Vite Proxy (:5173/api) -> FastAPI (:8000) -> PostgreSQL Database.
 *
 * Uses the dedicated E2E test account (`e2e.admin@doculens.ai`) seeded by `e2e/global-setup.ts`.
 */
test.describe("Full-Stack Smoke Journey (@fullstack)", () => {
  test("authenticates against live FastAPI backend, loads workspace, and verifies DB user list", async ({
    page,
  }) => {
    // 1. Navigate to the login page and sign in with the dedicated E2E test user
    await page.goto("/login");
    await page.getByLabel("Email address").fill(E2E_ADMIN_EMAIL);
    await page.getByLabel("Password").fill(E2E_ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    // 2. Verify real JWT authentication succeeded and routed to `/documents`
    await expect(page).toHaveURL(/\/documents$/);
    await expect(
      page.getByRole("heading", { name: "Documents", exact: true }),
    ).toBeVisible();

    // 3. Navigate to `/admin/users` and verify our live PostgreSQL user record renders
    await page.goto("/admin/users");
    await expect(
      page.getByRole("heading", { name: "Users & Access Control" }),
    ).toBeVisible();
    await expect(
      page.getByText(E2E_ADMIN_EMAIL, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: new RegExp(E2E_ADMIN_NAME) }),
    ).toBeVisible();
  });
});
