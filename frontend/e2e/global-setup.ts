import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const E2E_ADMIN_EMAIL =
  process.env.E2E_ADMIN_EMAIL ?? "e2e.admin@doculens.ai";
export const E2E_ADMIN_PASSWORD =
  process.env.E2E_ADMIN_PASSWORD ?? "E2eTestPass12345!";
export const E2E_ADMIN_NAME = "E2E Test Admin";

/**
 * Playwright Global Setup (`e2e/global-setup.ts`).
 *
 * Runs once before all E2E test workers start.
 * Idempotently seeds or refreshes the dedicated E2E test user (`e2e.admin@doculens.ai`)
 * with `must_change_password=False` using `python -m app.create_admin`, leaving any
 * human administrator account untouched.
 */
export default async function globalSetup(): Promise<void> {
  const backendDir = path.resolve(__dirname, "../../backend");
  const winPython = path.join(backendDir, "venv", "Scripts", "python.exe");
  const posixPython = path.join(backendDir, "venv", "bin", "python");
  const pythonBin = fs.existsSync(winPython)
    ? winPython
    : fs.existsSync(posixPython)
      ? posixPython
      : "python";

  try {
    execFileSync(
      pythonBin,
      [
        "-m",
        "app.create_admin",
        "--email",
        E2E_ADMIN_EMAIL,
        "--password",
        E2E_ADMIN_PASSWORD,
        "--full-name",
        E2E_ADMIN_NAME,
        "--no-must-change-password",
      ],
      {
        cwd: backendDir,
        stdio: "pipe",
        timeout: 30_000,
      },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.warn(
      `[Playwright globalSetup] Warning: Could not seed E2E user (${message}). ` +
        "Mocked E2E tests will still run, but live @fullstack tests require database access.",
    );
  }
}

