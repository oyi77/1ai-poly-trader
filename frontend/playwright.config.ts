import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Run sequentially for better debugging
  forbidOnly: !!process.env.CI,
  retries: 0, // No retries for debugging
  workers: 1, // Single worker for debugging
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_TEST_BASE_URL || 'http://localhost:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    timeout: 60000, // 60s timeout for long operations
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Disable acceleration for headless debugging
        launchOptions: {
          args: ['--disable-dev-shm-usage', '--no-sandbox']
        }
      },
    },
  ],

  // Local webServer for development, production server via tunnel in CI
  webServer: process.env.CI ? undefined : {
    command: 'npm run preview',
    url: 'http://localhost:5174',
    reuseExistingServer: true,
    timeout: 120000,
  }
})
