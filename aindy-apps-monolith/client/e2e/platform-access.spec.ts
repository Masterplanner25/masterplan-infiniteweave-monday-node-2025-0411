import { expect, test } from "./fixtures";
import { LoginPage } from "./pages/LoginPage";
import { HealthPage } from "./pages/HealthPage";

async function clearSession(page) {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
}

test("non-admin cannot access /platform/health and is redirected", async ({ page, setupMocks }) => {
  await setupMocks({ isAdmin: false });
  const healthPage = new HealthPage(page);
  await healthPage.goto();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText(/admin access required/i)).not.toBeVisible();
});

test("admin can access /platform/health", async ({ page, setupMocks }) => {
  await setupMocks({ isAdmin: true });
  await clearSession(page);
  await page.goto("/login");
  await new LoginPage(page).login("testuser@aindy.ai", "testpass");
  await expect(page).toHaveURL(/\/dashboard$/);

  const healthPage = new HealthPage(page);
  await healthPage.goto();
  await healthPage.expectLoaded();
  await healthPage.expectHealthy();
});

test("unauthenticated request to /platform/health redirects to login", async ({ page, setupMocks }) => {
  await setupMocks({ isAdmin: true });
  await clearSession(page);
  await page.goto("/platform/health");

  await expect(page).toHaveURL(/\/login$/);
});

test("platform sidebar links are correct after login as admin", async ({ page, setupMocks }) => {
  await setupMocks({ isAdmin: true });
  await clearSession(page);
  await page.goto("/login");
  await new LoginPage(page).login("testuser@aindy.ai", "testpass");
  await expect(page).toHaveURL(/\/dashboard$/);

  await expect(page.locator('a[href="/platform/flows"]')).toBeVisible();
  await expect(page.locator('a[href="/platform/approvals"]')).toBeVisible();
  await expect(page.locator('a[href="/platform/observability"]')).toBeVisible();
  await expect(page.locator('a[href="/platform/trace"]')).toBeVisible();
});
