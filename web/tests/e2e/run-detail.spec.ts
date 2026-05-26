import { test, expect } from "@playwright/test";

// The detail page is the artifact a reviewer drills into; the test mirrors what they see.
// Run #22 is the orchestrator run for 002-off-by-one — has 3 reflexion iterations, so it
// exercises the full Plan / Timeline / Verdict trio.

test.describe("run detail", () => {
  test("orchestrator run renders plan, timeline and verdict", async ({ page }) => {
    await page.goto("/runs/22");

    await expect(page.getByRole("heading", { name: /run #/i })).toBeVisible();
    await expect(page.getByText(/orchestrator/i).first()).toBeVisible();

    await expect(page.getByRole("heading", { name: /plan \(from the planner agent\)/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /reflexion timeline/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /final verdict/i })).toBeVisible();

    // The timeline must show as many cards as recorded iterations. Run 22 has 3.
    const iterations = page.getByText(/iteration \d+/i);
    expect(await iterations.count()).toBeGreaterThanOrEqual(3);
  });

  test("baseline (executor) run skips the planner section", async ({ page }) => {
    // Run #12 is executor-only on 002-off-by-one.
    await page.goto("/runs/12");
    await expect(page.getByRole("heading", { name: /executor-only run/i })).toBeVisible();
    await expect(page.getByText(/no planner or verifier/i)).toBeVisible();
  });

  test("404s gracefully for unknown ids", async ({ page }) => {
    const res = await page.goto("/runs/99999");
    expect(res?.status()).toBe(404);
  });

  test("back link returns to the home page", async ({ page }) => {
    await page.goto("/runs/22");
    await page.getByRole("link", { name: /all runs/i }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "issue-to-pr-agent" })).toBeVisible();
  });
});
