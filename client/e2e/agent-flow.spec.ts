import { expect, test } from "./fixtures";
import { AgentConsolePage } from "./pages/AgentConsolePage";
import { LoginPage } from "./pages/LoginPage";

async function loginAsAdmin(page, setupMocks) {
  await setupMocks({ isAdmin: true });
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.goto("/login");
  await new LoginPage(page).login("testuser@aindy.ai", "testpass");
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("agent submit-goal flow reaches pending approval state", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  const agentPage = new AgentConsolePage(page);
  await agentPage.goto();
  await agentPage.expectLoaded();

  await agentPage.submitGoal("Validate cross-domain event propagation");
  await agentPage.expectPendingApprovalVisible();
});

test("agent approval flow completes and shows timeline events", async ({ page, setupMocks }) => {
  await loginAsAdmin(page, setupMocks);
  const agentPage = new AgentConsolePage(page);
  await agentPage.goto();
  await agentPage.expectLoaded();

  await agentPage.submitGoal("Validate cross-domain event propagation");
  await agentPage.expectPendingApprovalVisible();

  await agentPage.approveRun();
  await expect(page.getByText(/completed/i).first()).toBeVisible({ timeout: 6000 });

  await agentPage.openTimeline();
  await agentPage.expectTimelineEventVisible("PLAN_CREATED");
  await agentPage.expectTimelineEventVisible("EXECUTION_STARTED");
});
