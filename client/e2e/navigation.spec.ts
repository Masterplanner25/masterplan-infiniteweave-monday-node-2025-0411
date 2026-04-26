import { test, expect } from "./fixtures";
import { AppShellPage } from "./pages/AppShellPage";
import { TasksPage } from "./pages/TasksPage";
import { MasterPlanPage } from "./pages/MasterPlanPage";

test("main navigation links are present and navigable", async ({ page, setupMocks }) => {
  await setupMocks();
  await page.goto("/tasks");

  const shell = new AppShellPage(page);
  await shell.expectWorkspaceNavigation();
  await shell.goToMasterPlan();

  const masterPlanPage = new MasterPlanPage(page);
  await expect(page).toHaveURL(/\/masterplan$/);
  await masterPlanPage.expectLoaded();
  await masterPlanPage.expectPlanVisible("V3 NORTHSTAR");

  await shell.goToTasks();
  const tasksPage = new TasksPage(page);
  await expect(page).toHaveURL(/\/tasks$/);
  await tasksPage.expectLoaded();
});

test("unknown routes redirect authenticated users to dashboard", async ({ page, setupMocks }) => {
  await setupMocks();
  await page.goto("/not-a-real-route");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("button", { name: /logout/i })).toBeVisible();
});
