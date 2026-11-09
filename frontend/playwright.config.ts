import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(__dirname, "../backend");
const winPython = path.join(backendDir, "venv", "Scripts", "python.exe");
const posixPython = path.join(backendDir, "venv", "bin", "python");
const pythonBin = fs.existsSync(winPython)
  ? `"${winPython}"`
  : fs.existsSync(posixPython)
    ? `"${posixPython}"`
    : "python";

/**
 * DocuLens Playwright E2E Configuration.
 *
 * Key concepts for first-time Playwright users:
 * - `globalSetup`: Runs once before the suite to seed the dedicated E2E test user.
 * - `timeout` & `globalTimeout`: Hard guardrails so a test run can never hang indefinitely.
 * - `webServer`: Array of servers `[FastAPI backend, Vite frontend]`.
 *   Playwright automatically starts (or reuses if already running) both servers!
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 30_000,
  globalTimeout: 180_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never" }]],

  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: [
    {
      command: `${pythonBin} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: backendDir,
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      // Invoke the Vite binary directly via `node` rather than `npm run dev` on Windows
      // so Playwright can cleanly terminate the process without leaving orphaned stdio pipes.
      command: "node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173",
      cwd: __dirname,
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
