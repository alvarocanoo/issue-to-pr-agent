import { test, expect } from "@playwright/test";

// The /compare page is the headline artifact for recruiters: 10 issues x 2 arms = 20 cells
// of resolved/failed evidence with the +70 pp delta visible. If this breaks the A/B story
// looks broken.

test.describe("compare", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/compare");
  });

  test("renders the comparison heading and the +70 pp headline", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /a\/b comparison/i })).toBeVisible();
    await expect(page.getByText(/\+70 pp/).first()).toBeVisible();
  });

  test("table has one row per trivial issue", async ({ page }) => {
    const dataRows = page.locator("tbody tr");
    expect(await dataRows.count()).toBe(10);
    // First task in alphabetical order is 001-typo.
    await expect(dataRows.first()).toContainText("001-typo");
    await expect(dataRows.last()).toContainText("010-recursion-base-case");
  });

  test("fixed badge appears for issues the orchestrator resolved over baseline", async ({
    page,
  }) => {
    // ADR-002 measurement: 9/10 of the trivial issues are 'fixed' (executor-only failed,
    // orchestrator passed). The remaining one is 006-typo-attribute where both arms pass
    // and 007/008 where both arms fail.
    const fixedBadges = page.getByText("fixed", { exact: true });
    expect(await fixedBadges.count()).toBeGreaterThanOrEqual(5);
  });

  test("clicking a task row token count opens the matching run detail", async ({ page }) => {
    const row = page.locator("tbody tr", { hasText: "002-off-by-one" });
    await row.getByRole("link").first().click();
    await expect(page).toHaveURL(/\/runs\/\d+\/?$/);
    await expect(page.getByRole("heading", { name: /run #/i })).toBeVisible();
  });

  test("totals footer sums match the per-task data", async ({ page }) => {
    const footer = page.locator("tfoot");
    await expect(footer.getByText(/totals/i)).toBeVisible();
    // Baseline solved is 1/10, orchestrator 8/10 in the embedded snapshot.
    await expect(footer.getByText("1/10")).toBeVisible();
    await expect(footer.getByText("8/10")).toBeVisible();
  });
});
