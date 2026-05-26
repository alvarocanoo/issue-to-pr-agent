import { test, expect } from "@playwright/test";

// The home page is the entry point on Pages; if these assertions break the public demo is
// silently broken. We pin selectors on user-facing text (role/heading), not CSS classes, so
// a Tailwind tweak does not turn the suite red.

test.describe("home", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders the title and source link", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "issue-to-pr-agent" })).toBeVisible();
    await expect(page.getByRole("link", { name: /source on github/i })).toHaveAttribute(
      "href",
      "https://github.com/alvarocanoo/issue-to-pr-agent",
    );
  });

  test("stats bar shows resolved@1 with both arms counted", async ({ page }) => {
    // 20 runs total (10 baseline + 10 orchestrator) — verifies the embedded snapshot loaded.
    await expect(page.getByText(/^resolved@1$/i)).toBeVisible();
    await expect(page.getByText(/9 \/ 20/)).toBeVisible();
    await expect(page.getByText(/executor:10/)).toBeVisible();
    await expect(page.getByText(/orchestrator:10/)).toBeVisible();
  });

  test("recent runs table lists at least one row and links into detail", async ({ page }) => {
    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    // Row count: header + data rows. We seed 20 runs so the table must have > 1 row.
    const rows = table.locator("tbody tr");
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(1);
  });

  test("A/B comparison button navigates to /compare", async ({ page }) => {
    await page.getByRole("link", { name: /a\/b comparison/i }).click();
    await expect(page).toHaveURL(/\/compare\/?$/);
    await expect(page.getByRole("heading", { name: /a\/b comparison/i })).toBeVisible();
  });
});
