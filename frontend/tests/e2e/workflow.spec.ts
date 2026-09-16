import { test, expect } from "@playwright/test";
import path from "node:path";

test("manager → synthetic document → invitation → consent → media → reports", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter synthetic demo" }).click();
  await page.getByLabel("Organization name").fill("Northstar Studio");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Your next great hire starts here." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create a job", exact: true })
    .first()
    .click();
  await page.getByLabel("Job title").fill("Backend engineer");
  await page
    .getByLabel("Job description")
    .fill(
      "Build reliable Python services with PostgreSQL, and explain design tradeoffs with a collaborative team.",
    );
  await page.getByLabel("Required skills").fill("Python, PostgreSQL, testing");
  await page.getByRole("button", { name: "Create role", exact: true }).click();
  await page.getByRole("button", { name: "Manage" }).click();
  await page
    .getByLabel("Import candidates CSV")
    .setInputFiles(path.resolve("test-fixtures/candidates.csv"));
  await expect(page.getByText("Alex Morgan", { exact: true })).toBeVisible();
  await page
    .getByLabel("Upload document for Alex Morgan")
    .setInputFiles(path.resolve("test-fixtures/resume.docx"));
  await expect(page.getByText(/resume.docx · ready/)).toBeVisible();
  await page.getByRole("button", { name: "Prepare interview" }).click();
  await page.getByRole("button", { name: "Review plan" }).click();
  await expect(
    page.getByRole("heading", { name: "Scoring rubric" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Approve interview plan" }).click();
  await page.getByLabel("Select Alex Morgan").check();
  await page.getByRole("button", { name: /Send invitations/ }).click();
  await expect(page.getByText("Invited", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/manager-candidates.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Notifications", exact: true })
    .click();
  const invitation = page
    .locator("article")
    .filter({ hasText: "Your Talyn interview invitation" });
  const link = await invitation
    .getByRole("link", { name: "Open secure link" })
    .getAttribute("href");
  const candidate = await context.newPage();
  await candidate.goto(link!);
  await candidate
    .getByRole("button", { name: "Send verification code" })
    .click();
  const verification = page
    .locator("article")
    .filter({ hasText: "Your Talyn verification code" })
    .first();
  await expect(verification).toBeVisible();
  const code = (await verification.locator("pre").innerText()).match(
    /\b\d{6}\b/,
  )![0];
  await candidate.getByLabel("Verification code").fill(code);
  await candidate.getByRole("button", { name: "Verify and continue" }).click();
  await candidate.getByLabel(/I understand the AI interview/).check();
  await candidate
    .getByRole("button", { name: "Check microphone & camera" })
    .click();
  await expect(candidate.getByText("Devices ready")).toBeVisible();
  await candidate
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await expect(
    candidate.getByRole("heading", { name: "One question at a time." }),
  ).toBeVisible();
  await candidate.screenshot({
    path: "test-results/candidate-interview.png",
    fullPage: true,
  });
  for (let i = 0; i < 6; i++) {
    if (
      await candidate
        .getByRole("heading", { name: "Your story has been heard." })
        .isVisible()
    )
      break;
    await candidate
      .getByLabel("Synthetic answer input")
      .fill(
        "I built a Python API with PostgreSQL transactions and idempotency keys. I compared two approaches with my team, tested failure cases, and measured performance. This reduced duplicate work by forty percent while preserving correctness and a clear audit trail.",
      );
    await candidate.getByRole("button", { name: "Finish answer" }).click();
    await expect(
      candidate.getByRole("button", { name: "Finish answer" }).or(
        candidate.getByRole("heading", {
          name: "Your story has been heard.",
        }),
      ),
    ).toBeVisible();
    await expect
      .poll(
        async () =>
          (await candidate
            .getByRole("heading", { name: "Your story has been heard." })
            .isVisible()) ||
          (await candidate
            .getByRole("button", { name: "Finish answer" })
            .isEnabled()
            .catch(() => false)),
      )
      .toBe(true);
  }
  await expect(
    candidate.getByRole("heading", { name: "Your story has been heard." }),
  ).toBeVisible();
  await expect(
    candidate.getByRole("heading", { name: "For your next conversation" }),
  ).toBeVisible();
  await expect(
    candidate.getByText("Recording verified", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Jobs & candidates", exact: true })
    .click();
  await page.getByRole("button", { name: "View report" }).click();
  await expect(
    page.getByRole("heading", { name: "Competency evidence" }),
  ).toBeVisible();
  await page
    .getByLabel("Private notes")
    .fill("Private manager note — never in candidate feedback");
  await page.getByRole("button", { name: "Save assessment" }).click();
  await candidate.reload();
  await expect(
    candidate.getByText("Private manager note — never in candidate feedback"),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Recordings", exact: true }).click();
  const video = page.locator("video");
  await expect(video).toBeVisible();
  await expect
    .poll(() =>
      video.evaluate((element: HTMLVideoElement) => element.readyState),
    )
    .toBeGreaterThanOrEqual(2);
  await page
    .getByRole("button", { name: "Notifications", exact: true })
    .click();
  await expect(
    page
      .locator("article")
      .filter({ hasText: "Your Talyn interview feedback is ready" }),
  ).toContainText("alex@example.com");
  await expect(
    page
      .locator("article")
      .filter({ hasText: "Interview report ready for review" }),
  ).toContainText("manager@example.test");
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.screenshot({
    path: "test-results/workspace-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(
    () => page.evaluate(() => ({
      width: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    })),
  ).toEqual({ width: 390, content: 390 });
  await page.screenshot({
    path: "test-results/workspace-mobile.png",
    fullPage: true,
  });
  await expect(
    page.getByRole("heading", { name: "Your next great hire starts here." }),
  ).toBeVisible();
});
