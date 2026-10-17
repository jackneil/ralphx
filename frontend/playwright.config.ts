import { randomBytes } from 'node:crypto'
import { defineConfig, devices } from '@playwright/test'

// The API requires the local access token. The test server gets this token
// from RALPHX_API_TOKEN, and every browser and API request sends it.
const apiToken = process.env.RALPHX_API_TOKEN ?? randomBytes(32).toString('base64url')
process.env.RALPHX_API_TOKEN = apiToken

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  timeout: 30000,

  use: {
    baseURL: 'http://localhost:8765',
    extraHTTPHeaders: { Authorization: `Bearer ${apiToken}` },
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'cd .. && python -m uvicorn ralphx.api.main:app --host 127.0.0.1 --port 8765',
    env: { RALPHX_API_TOKEN: apiToken },
    url: 'http://localhost:8765/api/health',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
})
