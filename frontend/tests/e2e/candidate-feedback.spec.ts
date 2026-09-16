import { test, expect } from "@playwright/test";

test("completed feedback explains missing suggestions and shows final answer evidence", async ({
  page,
}) => {
  const responses: Record<string, unknown> = {
    me: {
      csrf: "fixture",
      application_id: "completed-fixture",
      name: "Synthetic Alex",
      job_title: "Backend Engineer",
      recording_required: false,
      mode: "demo",
      session: {
        id: "session-fixture",
        status: "completed",
        question_index: 1,
        question_count: 1,
        question: null,
        turn: 1,
        silence_seconds: 10,
        started_at: "2026-09-16T10:00:00Z",
        deadline_at: "2026-09-16T10:10:00Z",
        server_time: "2026-09-16T10:11:00Z",
      },
    },
    transcript: [
      { id: "partial", text: "Unfinished draft words", final: false, turn: 0 },
      {
        id: "final-1",
        text: "I compared two database designs.",
        final: true,
        turn: 0,
      },
      {
        id: "final-2",
        text: "Then I tested concurrent requests.",
        final: true,
        turn: 0,
      },
      { id: "blank", text: " ", final: true, turn: 1 },
    ],
    report: {
      synthetic: false,
      competencies: ["Technical reasoning"],
      feedback: "Your example explained a database trade-off.",
      strengths: ["Clear trade-off discussion"],
      suggestions: [],
    },
    observations: [],
  };
  await page.route("**/api/candidate/*", async (route) => {
    const resource = new URL(route.request().url()).pathname.split("/").pop()!;
    await route.fulfill({ json: responses[resource] ?? {} });
  });
  await page.goto("/interview");
  await expect(
    page.getByRole("heading", { name: "Your interview feedback" }),
  ).toBeVisible();
  await expect(page.getByText("Synthetic Alex", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Backend Engineer", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No specific improvement suggestions were generated", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Clear trade-off discussion", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".feedback-answer")).toHaveCount(1);
  await expect(page.locator(".feedback-answer")).toContainText(
    "I compared two database designs. Then I tested concurrent requests.",
  );
  await expect(page.getByText("Unfinished draft words")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "What happens next" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/candidate-feedback-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBe(390);
  await page.screenshot({
    path: "test-results/candidate-feedback-mobile.png",
    fullPage: true,
  });
});
