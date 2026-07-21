import { defineConfig, devices } from '@playwright/test';

const slowMo = Number(process.env.PLAYWRIGHT_SLOW_MO ?? 0);
const port = process.env.PLAYWRIGHT_PORT ?? '9000';
const baseURL = `http://localhost:${port}`;
const chromiumUse = {
  ...devices['Desktop Chrome'],
  ...(process.env.PLAYWRIGHT_USE_SYSTEM_CHROME ? { channel: 'chrome' as const } : {}),
  ...(slowMo > 0 ? { launchOptions: { slowMo } } : {}),
};

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'html' : 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: chromiumUse,
    },
  ],
  webServer: {
    command: 'corepack pnpm start:dev',
    url: baseURL,
    env: {
      ...process.env,
      PORT: port,
    },
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
