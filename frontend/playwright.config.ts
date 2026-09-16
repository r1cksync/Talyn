import { defineConfig } from "@playwright/test";
import path from "node:path";
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120000,
  expect: { timeout: 20000 },
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        `--use-file-for-fake-video-capture=${path.resolve("test-fixtures/camera.y4m")}`,
        `--use-file-for-fake-audio-capture=${path.resolve("test-fixtures/audio.wav")}`,
      ],
    },
    permissions: ["camera", "microphone"],
    viewport: { width: 1440, height: 1000 },
  },
  webServer: [
    {
      command:
        "python -m uv run alembic upgrade head && python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 90000,
      env: { TALYN_MODE: "demo", TALYN_RUN_DEMO_WORKER: "true" },
    },
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 90000,
    },
  ],
});
