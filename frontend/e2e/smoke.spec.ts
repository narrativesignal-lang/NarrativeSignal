import { test, expect } from "@playwright/test";

test.describe("Smoke tests", () => {
  test("landing page loads", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Sign in" }).first()).toBeVisible({ timeout: 15_000 });
  });

  test("login page loads", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator('input[type="password"]')).toBeVisible({ timeout: 10_000 });
  });

  test.skip("auth modal does not close on backdrop click", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: /sign in/i }).first().click();
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    const input = dialog.locator('input[type="text"]').first();
    await input.fill("testuser");
    await dialog.click({ position: { x: 5, y: 5 } });
    await expect(dialog).toBeVisible();
    await expect(input).toHaveValue("testuser");
  });

  test("dashboard redirects to login when unauthenticated", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/(login|\?|$)/, { timeout: 10_000 });
  });

  test("research page redirects to login when unauthenticated", async ({ page }) => {
    await page.goto("/research");
    await expect(page).toHaveURL(/\/(login|\?|$)/, { timeout: 10_000 });
  });
});

test.describe("Authenticated flows", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/login");
    await page.waitForSelector('input:not([type="password"])', { state: "visible", timeout: 15_000 });
    await page.fill('input:not([type="password"])', "admin");
    await page.fill('input[type="password"]', "admin");
    await page.locator("form").getByRole("button", { name: /Sign in|Register \+ sign in/i }).click();
    await expect(page).toHaveURL(/dashboard/, { timeout: 20_000 });
  });

  test("dashboard shows macro tab and market data area", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText("Index watchlist").first()).toBeVisible({ timeout: 15_000 });
  });

  test("research page loads with sidebar", async ({ page }) => {
    await page.goto("/research");
    const headingOrEmpty = page.getByRole("heading", { name: "Cross Comparison" }).or(page.getByText("No project selected"));
    await expect(headingOrEmpty.first()).toBeVisible({ timeout: 15_000 });
  });

  test("research instrument search has category filters", async ({ page }) => {
    await page.goto("/research");
    const createProject = page.getByRole("button", { name: /create|new project/i }).or(page.locator("text=+ "));
    if (await createProject.isVisible()) await createProject.click();
    const addInstrument = page.locator("text=+ Add instrument").first();
    if (await addInstrument.isVisible()) {
      await addInstrument.click();
      await page.fill('input[placeholder*="Search"], input[placeholder*="symbol"]', "AAPL");
      await expect(page.locator("text=Stock").or(page.locator("text=All"))).toBeVisible({ timeout: 5_000 });
    }
  });
});
