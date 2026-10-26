import os from "node:os";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// Browser E2E runs against a dedicated stack: the backend on its own port
// with the disposable `oneflowai_e2e` database (re-seeded by global setup),
// and the Next.js dev server proxying /api/v1 to it. The development
// database and the pytest database are never touched.
const BACKEND_PORT = 8100;
const FRONTEND_PORT = 3100;
const E2E_DATABASE = "oneflowai_e2e";
// Seed credentials and run artefacts stay outside the repository.
process.env.E2E_SEED_PATH ??= path.join(os.tmpdir(), "oneflowai-e2e-seed.json");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  outputDir: path.join(os.tmpdir(), "oneflowai-e2e-results"),
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    locale: "en-US",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `.venv\\Scripts\\python.exe -m uvicorn app.main:app --port ${BACKEND_PORT}`,
      cwd: "../backend",
      env: { POSTGRES_DB: E2E_DATABASE },
      url: `http://localhost:${BACKEND_PORT}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npx next dev -p ${FRONTEND_PORT}`,
      env: {
        BACKEND_URL: `http://localhost:${BACKEND_PORT}`,
        // Keep every browser call on the same-origin proxy to the E2E backend,
        // overriding any absolute API URL in .env.local.
        NEXT_PUBLIC_API_URL: "/api/v1",
      },
      url: `http://localhost:${FRONTEND_PORT}/login`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
