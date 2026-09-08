import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';
const python = resolve(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python');
export default defineConfig({
  testDir: './streamlit/e2e', timeout: 90000, workers: 1,
  expect: { timeout: 15000 },
  use: {baseURL:'http://127.0.0.1:18501', viewport:{width:1440,height:1000}, trace:'retain-on-failure', screenshot:'only-on-failure'},
  webServer: [
    { command:`"${python}" -m scripts.serve_streamlit_test`, cwd:resolve('..'), url:'http://127.0.0.1:18765/health', reuseExistingServer:!process.env.CI, timeout:30000 },
    { command:`"${python}" -m streamlit run frontend/app.py --server.port 18501 --server.headless true --server.fileWatcherType none --browser.gatherUsageStats false`, cwd:resolve('..'), env:{OJ_API_URL:'http://127.0.0.1:18765'}, url:'http://127.0.0.1:18501/_stcore/health', reuseExistingServer:!process.env.CI, timeout:30000 },
  ],
});
