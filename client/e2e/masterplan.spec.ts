import { expect, test } from "./fixtures";
import { LoginPage } from "./pages/LoginPage";
import { MasterPlanPage } from "./pages/MasterPlanPage";

async function loginAsUser(page, setupMocks) {
  await setupMocks({ isAdmin: false });
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.goto("/login");
  await new LoginPage(page).login("testuser@aindy.ai", "testpass");
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("masterplan page loads with plans and projection visible", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  const masterPlanPage = new MasterPlanPage(page);
  await masterPlanPage.goto();
  await masterPlanPage.expectLoaded();
  await masterPlanPage.expectPlanVisible("V3 NORTHSTAR");
  await masterPlanPage.expectPlanVisible("V4 ACTIVE ARC");
  await expect(page.getByText(/ETA PROJECTION/i)).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/2026-05-30/)).toBeVisible({ timeout: 5000 });
});

test("activating a locked plan updates its status", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  const masterPlanPage = new MasterPlanPage(page);
  await masterPlanPage.goto();
  await masterPlanPage.expectLoaded();
  await masterPlanPage.expectPlanVisible("V3 NORTHSTAR");

  await masterPlanPage.activatePlan();

  const northstarCard = page
    .locator("div")
    .filter({ has: page.getByText("V3 NORTHSTAR", { exact: true }) })
    .filter({ has: page.getByText(/^ACTIVE$/, { exact: true }) })
    .first();
  await expect(northstarCard).toBeVisible({ timeout: 5000 });
});

test("anchor modal opens and saves an anchor date", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  const masterPlanPage = new MasterPlanPage(page);
  await masterPlanPage.goto();
  await masterPlanPage.expectLoaded();

  await masterPlanPage.openAnchorModal();
  await masterPlanPage.expectAnchorDialogVisible();

  await page.locator('input[type="date"]').fill("2026-06-15");
  await page.getByRole("button", { name: /save anchor/i }).click();

  await expect(page.getByRole("heading", { name: /set anchor/i })).toBeHidden({ timeout: 5000 });
  await masterPlanPage.expectPlanVisible("V4 ACTIVE ARC");
});
