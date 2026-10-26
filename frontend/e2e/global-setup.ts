import { execFileSync } from "node:child_process";
import path from "node:path";

// Recreates and seeds the dedicated E2E database through the backend's own
// test helpers (tests/e2e_seed.py refuses any database not named *_e2e).
export default function globalSetup() {
  const backend = path.resolve(__dirname, "..", "..", "backend");
  execFileSync(
    path.join(backend, ".venv", "Scripts", "python.exe"),
    ["-m", "pytest", "tests/e2e_seed.py", "-p", "no:cacheprovider", "-q", "-W", "ignore"],
    {
      cwd: backend,
      stdio: "inherit",
      env: {
        ...process.env,
        TEST_DATABASE_URL:
          "postgresql+asyncpg://oneflowai:oneflowai@localhost:5432/oneflowai_e2e",
        E2E_SEED_OUT: process.env.E2E_SEED_PATH,
      },
    },
  );
}
