import { defineConfig } from '@playwright/test'
import path from 'node:path'

export default defineConfig({
  testDir: './e2e', workers: 1, retries: 0, timeout: 90000,
  use: { baseURL: 'http://127.0.0.1:19090', browserName: 'chromium', viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  reporter: [['list'], ['html', { open: 'never' }]],
  webServer: [
    { command: `${process.env.SENTINEL_TEST_PYTHON || '../backend/.venv/bin/python'} ../tests/e2e_backend.py`, url: 'http://127.0.0.1:19091/api/health', reuseExistingServer: false, timeout: 30000 },
    { command: 'node server.mjs', url: 'http://127.0.0.1:19090/healthz', reuseExistingServer: false, timeout: 30000, env: { SENTINEL_WEB_HOST: '127.0.0.1', SENTINEL_WEB_PORT: '19090', SENTINEL_API_URL: 'http://127.0.0.1:19091' } },
  ],
})
