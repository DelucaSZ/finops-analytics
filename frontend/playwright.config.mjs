import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: "chromium-mobile",
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: "npm run start -- -H 127.0.0.1 -p 3000",
    url: "http://127.0.0.1:3000/login",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
