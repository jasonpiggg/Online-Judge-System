import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `"${resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python")}" ../scripts/serve_web_test.py`,
    url: "http://127.0.0.1:8765/health",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium", viewport: { width: 1440, height: 1000 } },
    },
  ],
});
