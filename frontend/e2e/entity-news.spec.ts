/**
 * NVDA / entity news panel — requires backend + seeded instruments.
 * Single auth path: UI login only; API calls use page.request + Bearer from localStorage (same session, no second login).
 */
import { test, expect, type Page } from "@playwright/test";

async function bearerHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem("narrative_access_token"));
  expect(token, "expected access token in localStorage after UI login").toBeTruthy();
  return {
    Authorization: `Bearer ${token!}`,
    "Content-Type": "application/json",
  };
}

test.describe("Entity News panel (E2E)", () => {
  test("NVDA target news, keyword tab, empty keywords entity, no duplicate target fetches", async ({ page }) => {
    test.setTimeout(120_000);

    let targetNews = 0;
    let keywordNews = 0;
    page.on("request", (req) => {
      const u = req.url();
      if (!u.includes("/api/entities/") || !u.includes("/news")) return;
      if (u.includes("mode=target")) targetNews += 1;
      if (u.includes("mode=keywords")) keywordNews += 1;
    });

    await page.goto("/login");
    await page.locator('input:not([type="password"])').first().fill("admin");
    await page.locator('input[type="password"]').fill("admin");
    await page.locator("form").getByRole("button", { name: /Sign in|登录/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 25_000 });

    const h = await bearerHeaders(page);

    const pls = await page.request.get("/api/portfolios", { headers: h });
    expect(pls.ok(), await pls.text()).toBeTruthy();
    let portfolios = (await pls.json()) as { id: string }[];
    let portId: string;
    if (!portfolios.length) {
      const cr = await page.request.post("/api/portfolios", {
        headers: h,
        data: JSON.stringify({ name: "E2E News", description: null }),
      });
      expect(cr.ok(), await cr.text()).toBeTruthy();
      portId = ((await cr.json()) as { id: string }).id;
    } else {
      portId = portfolios[0].id;
    }

    const search = await page.request.get("/api/instruments/search?q=NVDA", { headers: h });
    expect(search.ok(), await search.text()).toBeTruthy();
    const hits = (await search.json()) as { id: string; symbol: string }[];
    expect(hits.length, "NVDA should exist in instrument seed").toBeGreaterThan(0);
    const instId = hits[0].id;

    const entRes = await page.request.get(`/api/portfolios/${portId}/entities`, { headers: h });
    expect(entRes.ok()).toBeTruthy();
    const entities = (await entRes.json()) as {
      id: string;
      instrument?: { symbol?: string };
      terms?: { term: string }[];
    }[];

    let nvdaEntity = entities.find((e) => e.instrument?.symbol?.toUpperCase() === "NVDA");
    if (!nvdaEntity) {
      const cr = await page.request.post("/api/entities", {
        headers: h,
        data: JSON.stringify({
          portfolio_id: portId,
          name: "NVIDIA E2E",
          instrument_id: instId,
          terms: ["AI", "GPU"],
        }),
      });
      expect(cr.ok(), await cr.text()).toBeTruthy();
      nvdaEntity = (await cr.json()) as { id: string };
    }

    expect(nvdaEntity).toBeTruthy();
    const entityId = nvdaEntity!.id;

    await page.goto(`/dashboard/entities/${entityId}`);
    const newsPanel = page.getByTestId("entity-news-panel");
    await expect(newsPanel).toBeVisible({ timeout: 30_000 });

    await expect.poll(() => targetNews, { timeout: 60_000 }).toBeGreaterThanOrEqual(1);

    const firstLink = newsPanel.locator('a[href^="http"]').first();
    await expect(firstLink).toBeVisible({ timeout: 90_000 });
    const href = await firstLink.getAttribute("href");
    expect(href).toMatch(/^https?:\/\//);

    const targetCount = targetNews;
    await page.getByRole("button", { name: /Keyword news|关键词资讯/ }).click();
    await expect.poll(() => keywordNews, { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
    expect(targetNews, "switching tab should not re-fetch target").toBe(targetCount);

    await page.getByRole("button", { name: /Target news|标的资讯/ }).click();
    expect(targetNews, "switch back to target should use client cache").toBe(targetCount);

    await page.getByRole("button", { name: /刷新|Refresh/ }).click();
    await expect.poll(() => targetNews).toBeGreaterThan(targetCount);

    const h2 = await bearerHeaders(page);
    const emptyKw = await page.request.post("/api/entities", {
      headers: h2,
      data: JSON.stringify({
        portfolio_id: portId,
        name: "No keywords E2E",
        instrument_id: instId,
        terms: [],
      }),
    });
    expect(emptyKw.ok(), await emptyKw.text()).toBeTruthy();
    const emptyEntity = (await emptyKw.json()) as { id: string };

    await page.goto(`/dashboard/entities/${emptyEntity.id}`);
    await expect(page.getByTestId("entity-news-panel")).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: /Keyword news|关键词资讯/ }).click();
    const emptyHint = page.getByText(/No keywords yet|暂无关键词/);
    await expect(emptyHint).toBeVisible({ timeout: 15_000 });

    const h3 = await bearerHeaders(page);
    const apiNews = await page.request.get(`/api/entities/${entityId}/news?mode=target`, { headers: h3 });
    expect(apiNews.ok(), await apiNews.text()).toBeTruthy();
    const payload = (await apiNews.json()) as { items: unknown[]; error: string | null; query: string | null };
    expect(payload.error).toBeNull();
    expect(payload.query).toBeTruthy();
    expect(payload.items?.length).toBeGreaterThan(0);
  });
});
