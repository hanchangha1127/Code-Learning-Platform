import { defineConfig } from "@playwright/test";

const runtimeEnv = {
  APP_ENV: "test",
  DB_PASSWORD: "test-db-password",
  JWT_SECRET: "test-jwt-secret-value-12345678901234567890",
  DB_HOST: "127.0.0.1",
  DB_PORT: "3306",
  DB_NAME: "code_platform",
  DB_USER: "appuser",
  ADMIN_PANEL_KEY: "test-admin-key-1234567890",
};

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8000",
    headless: true,
  },
  webServer: {
    command: "python -m server_runtime.runtime_server --host 127.0.0.1 --port 8000",
    url: "http://127.0.0.1:8000/health",
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
    env: runtimeEnv,
  },
});
