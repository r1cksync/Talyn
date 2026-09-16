import { test, expect } from "@playwright/test";

test("landing navigation, motion preference and responsive workspace", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Better questions",
  );
  await expect(
    page.getByRole("button", { name: "Enable decorative motion" }),
  ).toHaveAttribute("aria-pressed", "false");
  await page.screenshot({
    path: "test-results/landing-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Open your workspace" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByLabel("Work email")).toBeVisible();
  await page.goto("/");
  await page.locator("summary").first().click();
  await expect(
    page.getByText("Assessments link to transcript excerpts.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.screenshot({
    path: "test-results/landing-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.getByRole("link", { name: "Open your workspace" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(
    page.getByRole("button", { name: "Enter synthetic demo" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/auth-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
