import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "demo.spec.ts",
  timeout: 180_000,
  use: {
    baseURL: "http://127.0.0.1:5175",
    trace: "retain-on-failure",
    launchOptions: { slowMo: Number(process.env.DEMO_SLOW_MO_MS ?? "250") },
    ...devices["Desktop Chrome"],
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5175 --strictPort",
    url: "http://127.0.0.1:5175",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
