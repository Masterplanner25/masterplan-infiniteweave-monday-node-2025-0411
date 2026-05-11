import { expect, test } from "./fixtures";
import { GenesisPage } from "./pages/GenesisPage";
import { LoginPage } from "./pages/LoginPage";

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

test("genesis session starts and accepts a message", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  const genesisPage = new GenesisPage(page);
  await genesisPage.goto();
  await genesisPage.expectLoaded();
  await genesisPage.startSession();
  await genesisPage.expectSessionActive();
  await genesisPage.sendMessage("I want to build a sustainable SaaS business");
  await genesisPage.expectResponseVisible();
});

test("genesis flow reaches synthesized draft and locked plan", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  const genesisPage = new GenesisPage(page);
  await genesisPage.goto();
  await genesisPage.expectLoaded();
  await genesisPage.startSession();
  await genesisPage.expectSessionActive();
  await genesisPage.sendMessage("I want to build a sustainable SaaS business");
  await genesisPage.expectResponseVisible();
  await genesisPage.synthesize();
  await genesisPage.expectDraftVisible();
  await genesisPage.lockPlan();
  await genesisPage.expectPlanLocked();
});
