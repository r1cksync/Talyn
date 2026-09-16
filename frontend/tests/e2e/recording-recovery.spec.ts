import { test, expect } from "@playwright/test";

test("a stalled upload drains every saved clip and recording can resume", async ({
  page,
}) => {
  const started = Date.now();
  const session = {
    id: "recording-recovery-fixture",
    status: "active",
    turn: 0,
    question_index: 0,
    question_count: 3,
    question: {
      id: "q1",
      text: "Describe a technical project and explain your decisions.",
      competency: "Technical reasoning",
    },
    started_at: new Date(started).toISOString(),
    deadline_at: new Date(started + 600000).toISOString(),
    server_time: new Date(started).toISOString(),
    silence_seconds: 8,
  };
  await page.addInitScript(() => {
    // Deterministic capture isolates upload recovery from camera hardware and codec timing.
    class FixtureRecorder {
      static isTypeSupported() {
        return true;
      }
      state = "inactive";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() {
        this.state = "recording";
      }
      stop() {
        this.state = "inactive";
        queueMicrotask(() => {
          this.ondataavailable?.({
            data: new Blob([new Uint8Array([26, 69, 223, 163, 1])], {
              type: "video/webm",
            }),
          });
          this.onstop?.();
        });
      }
    }
    window.MediaRecorder = FixtureRecorder as unknown as typeof MediaRecorder;
    navigator.mediaDevices.getUserMedia = async () => new MediaStream();
  });
  await page.clock.install();
  let release!: () => void;
  const stalled = new Promise<void>((resolve) => {
    release = resolve;
  });
  // The server deduplicates retries by session and sequence, including a timed-out request.
  const uploaded = new Set<number>();
  let firstRequest = false;
  await page.route("**/api/candidate/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/me"))
      return route.fulfill({
        json: {
          csrf: "fixture",
          application_id: "application-fixture",
          name: "Synthetic Alex",
          job_title: "Backend Engineer",
          mode: "demo",
          recording_required: true,
          frame_interval_seconds: 30,
          session,
        },
      });
    if (path.endsWith("/session")) return route.fulfill({ json: session });
    if (path.endsWith("/transcript")) return route.fulfill({ json: [] });
    if (path.endsWith("/recordings/status"))
      return route.fulfill({
        json: { next_sequence: Math.max(-1, ...uploaded) + 1, clips: [] },
      });
    if (path.endsWith("/recordings")) {
      const clip = route.request().postDataJSON();
      if (clip.sequence === 0) {
        firstRequest = true;
        await stalled;
      }
      uploaded.add(clip.sequence);
      return route.fulfill({
        json: { id: `clip-${clip.sequence}`, verified: true },
      });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto("/interview");
  await page.getByRole("button", { name: "Reconnect devices" }).click();
  for (let index = 0; index < 4; index++) {
    await page.clock.runFor(10020);
    // Allow IndexedDB transactions to finish before advancing the next capture timer.
    await expect
      .poll(() =>
        page.evaluate(async () => {
          const db = await new Promise<IDBDatabase>((resolve) => {
            const request = indexedDB.open("talyn-pending-media", 1);
            request.onsuccess = () => resolve(request.result);
          });
          const count = await new Promise<number>((resolve) => {
            const request = db
              .transaction("clips")
              .objectStore("clips")
              .count();
            request.onsuccess = () => resolve(request.result);
          });
          db.close();
          return count;
        }),
      )
      .toBe(index + 1);
  }
  expect(firstRequest).toBe(true);
  await expect(
    page.getByRole("button", { name: "Retry uploads and resume" }),
  ).toBeVisible();
  await expect(
    page.getByText("Recording paused", { exact: true }),
  ).toBeVisible();
  release();
  await expect.poll(() => [...uploaded]).toEqual([0, 1, 2, 3]);
  await page.getByRole("button", { name: "Retry uploads and resume" }).click();
  await expect(
    page.getByRole("button", { name: "Retry uploads and resume" }),
  ).toHaveCount(0);
  await page.clock.runFor(10020);
  await expect.poll(() => [...uploaded]).toEqual([0, 1, 2, 3, 4]);
});

test("completed interview can retry saved uploads without camera access", async ({
  page,
}) => {
  let allowUpload = false;
  let finalized = false;
  const now = new Date().toISOString();
  await page.addInitScript(async () => {
    const db = await new Promise<IDBDatabase>((resolve) => {
      const request = indexedDB.open("talyn-pending-media", 1);
      request.onupgradeneeded = () =>
        request.result.createObjectStore("clips", { keyPath: "key" });
      request.onsuccess = () => resolve(request.result);
    });
    const tx = db.transaction("clips", "readwrite");
    tx.objectStore("clips").put({
      key: "completed-fixture:0",
      session: "completed-fixture",
      sequence: 0,
      blob: new Blob(["synthetic saved clip"], { type: "video/webm" }),
      start_ms: 0,
      end_ms: 1000,
      content_type: "video/webm",
    });
    await new Promise<void>((resolve) => {
      tx.oncomplete = () => resolve();
    });
    db.close();
    navigator.mediaDevices.getUserMedia = async () => {
      throw new Error("Camera must not be requested during recovery");
    };
  });
  await page.route("**/api/candidate/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/me"))
      return route.fulfill({
        json: {
          csrf: "fixture",
          application_id: "completed-app",
          name: "Synthetic Alex",
          job_title: "Backend Engineer",
          mode: "demo",
          recording_required: true,
          session: {
            id: "completed-fixture",
            status: "completed",
            started_at: now,
            deadline_at: now,
            server_time: now,
            turn: 1,
            question: null,
            question_count: 1,
            question_index: 1,
          },
        },
      });
    if (path.endsWith("/recordings/status"))
      return route.fulfill({ json: { next_sequence: 0, clips: [] } });
    if (path.endsWith("/recordings"))
      return route.fulfill(
        allowUpload
          ? { json: { id: "saved-clip", verified: true } }
          : { status: 503, json: { detail: "Temporary test outage" } },
      );
    if (path.endsWith("/finalize-manifest")) {
      expect(route.request().postDataJSON().expected_clips).toBe(1);
      finalized = true;
      return route.fulfill({ json: { finalized: true } });
    }
    if (path.endsWith("/report"))
      return route.fulfill({ status: 404, json: {} });
    return route.fulfill({ json: [] });
  });
  await page.goto("/interview");
  await expect(
    page.getByRole("button", { name: "Retry saved uploads" }),
  ).toBeVisible();
  expect(finalized).toBe(false);
  allowUpload = true;
  await page.getByRole("button", { name: "Retry saved uploads" }).click();
  await expect(
    page.getByText("Recording verified", { exact: true }),
  ).toBeVisible();
  expect(finalized).toBe(true);
});
