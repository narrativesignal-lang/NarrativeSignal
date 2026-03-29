/**
 * Requires Postgres + Redis + backend on PW_BACKEND_URL (default http://127.0.0.1:8000)
 * and Next dev on baseURL (reuseExistingServer).
 */
import { test, expect } from "@playwright/test";

const BACKEND = process.env.PW_BACKEND_URL ?? "http://127.0.0.1:8000";

async function loginJson(request: import("@playwright/test").APIRequestContext, email: string, password: string) {
  const res = await request.post(`${BACKEND}/api/auth/login`, {
    headers: { "Content-Type": "application/json" },
    data: JSON.stringify({ email, password }),
  });
  return res;
}

test.describe("Registration + rate limit (E2E)", () => {
  test("health: backend up", async ({ request }) => {
    const hz = await request.get(`${BACKEND}/healthz`);
    expect(hz.ok(), await hz.text()).toBeTruthy();
  });

  test("first-time register then login via UI (zh)", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("narrative_lang", "zh");
    });
    const email = `e2e_reg_${Date.now()}@example.com`;
    const password = "e2e-register-8chars";

    await page.goto("/login");
    await page.getByRole("button", { name: "注册" }).click();
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill(password);

    await page.locator("form").getByRole("button", { name: "注册并登录" }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 25_000 });
  });

  test("double-click submit sends only one register request", async ({ page }) => {
    const email = `e2e_dbl_${Date.now()}@example.com`;
    const password = "e2e-dblclk-8";

    const hits: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/api/auth/register") && req.method() === "POST") {
        hits.push(req.url());
      }
    });

    await page.goto("/login");
    await page.getByRole("button", { name: "Register" }).click();
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill(password);

    const submit = page.locator("form").getByRole("button", { name: /Register \+ sign in/i });
    await submit.dblclick();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 25_000 });
    expect(hits.length, `expected 1 POST register, got ${hits.length}`).toBe(1);
  });

  test("burst register triggers 429 from API", async ({ request }) => {
    const attempts = 50;
    let saw429 = false;
    for (let i = 0; i < attempts; i++) {
      const res = await request.post(`${BACKEND}/api/auth/register`, {
        headers: { "Content-Type": "application/json" },
        data: JSON.stringify({
          email: `burst_${Date.now()}_${i}@example.com`,
          password: "burstpass-8x",
        }),
      });
      if (res.status() === 429) {
        saw429 = true;
        const body = await res.text();
        expect(body.toLowerCase()).toContain("rate");
        break;
      }
      expect(res.status(), await res.text()).toBeLessThan(500);
    }
    expect(saw429, "dev register cap should yield at least one 429 in 50 tries from same IP").toBe(true);
  });

  test("429 on login page shows Chinese friendly text (not raw English)", async ({ page, request }) => {
    await page.addInitScript(() => {
      localStorage.setItem("narrative_lang", "zh");
    });

    for (let i = 0; i < 100; i++) {
      const res = await loginJson(request, "admin", "wrong");
      if (res.status() === 429) break;
    }

    await page.goto("/login");
    await page.locator('input:not([type="password"])').first().fill("admin");
    await page.locator('input[type="password"]').fill("admin");
    await page.locator("form").getByRole("button", { name: "登录" }).click();

    const err = page.locator(".text-red-200");
    await expect(err).toBeVisible({ timeout: 15_000 });
    const text = (await err.textContent()) ?? "";
    expect(text.length).toBeGreaterThan(3);
    expect(text.toLowerCase()).not.toContain("rate limit exceeded");
    expect(text).toMatch(/频繁|稍后再试|几秒/);
  });
});
