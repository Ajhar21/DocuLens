import { createMockUser, expect, test } from "./fixtures/auth";

/**
 * E2E Suite 2: Role-Based Access Control (RBAC) & User Administration (`rbac-navigation.spec.ts`)
 *
 * Demonstrates:
 * - Reusing the custom `loginAsRole` fixture to start tests already authenticated
 * - Verifying `ProtectedRoute` permission boundaries (`user:manage`)
 * - Testing interactive Radix Dialog modals & form submission (`Invite User`)
 */
test.describe("Role-Based Access Control & Admin User Management", () => {
  test("blocks non-admin role (FINANCE_EXECUTIVE) from accessing /admin/users", async ({
    page,
    loginAsRole,
  }) => {
    await loginAsRole("FINANCE_EXECUTIVE", {
      email: "exec@doculens.ai",
      full_name: "Finance Exec",
    });

    await page.goto("/admin/users");

    await expect(page.getByText("Access Restricted")).toBeVisible();
    await expect(
      page.getByText(/does not have the 'user:manage' permission/i),
    ).toBeVisible();
  });

  test("allows SYSTEM_ADMIN to view users and generate a single-use invitation link", async ({
    page,
    loginAsRole,
  }) => {
    const adminUser = await loginAsRole("SYSTEM_ADMIN", {
      email: "admin@doculens.ai",
      full_name: "Ada Lovelace",
    });

    const invitedUser = createMockUser({
      id: "00000000-0000-4000-8000-000000000099",
      email: "new.auditor@doculens.ai",
      full_name: "Alan Turing",
      role: "ACCOUNTS_AUDIT",
      is_active: false,
      status: "invited",
      last_login_at: null,
    });

    let currentUsers = [adminUser];

    await page.route("**/api/admin/users", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: currentUsers,
          error: null,
        }),
      });
    });

    await page.route("**/api/audit-logs?*", async (route) => {
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

    await page.route("**/api/admin/users/invite", async (route) => {
      currentUsers = [adminUser, invitedUser];
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            user: invitedUser,
            invite_token: "mock-csprng-invite-token-xyz",
            invite_url:
              "http://127.0.0.1:5173/accept-invite?token=mock-csprng-invite-token-xyz",
            expires_at: "2026-11-13T00:00:00Z",
          },
          error: null,
        }),
      });
    });

    await page.goto("/admin/users");

    await expect(
      page.getByRole("heading", { name: "Users & Access Control" }),
    ).toBeVisible();
    await expect(page.getByText("admin@doculens.ai")).toBeVisible();

    // Open the Invite User modal dialog
    await page.getByRole("button", { name: "Invite User" }).click();

    const dialog = page.getByRole("dialog", {
      name: "Invite User to DocuLens",
    });
    await expect(dialog).toBeVisible();

    // Fill out the invitation form
    await dialog.getByLabel("Email address").fill("new.auditor@doculens.ai");
    await dialog.getByLabel("Full name (optional)").fill("Alan Turing");
    await dialog.getByLabel("Assigned role").selectOption("ACCOUNTS_AUDIT");
    await dialog.getByRole("button", { name: "Create Invite Link" }).click();

    // Verify the one-time link dialog opens with the generated URL
    await expect(
      page.getByRole("dialog", { name: "Single-Use Invitation Link" }),
    ).toBeVisible();
    await expect(page.getByLabel("One-time action URL")).toHaveValue(
      "http://127.0.0.1:5173/accept-invite?token=mock-csprng-invite-token-xyz",
    );

    // Close the link dialog and verify the new user row appears in the table
    await page.getByRole("button", { name: "Done" }).click();
    await expect(
      page.getByText("new.auditor@doculens.ai", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Invited", { exact: true })).toBeVisible();
  });
});
