import { test, expect } from "./fixtures";
import { TasksPage } from "./pages/TasksPage";

test("displays task list after login", async ({ page, setupMocks }) => {
  await setupMocks();
  const tasksPage = new TasksPage(page);
  await tasksPage.goto();
  await tasksPage.expectLoaded();
  await tasksPage.expectTaskVisible("Calibrate agent loop");
  await tasksPage.expectTaskVisible("Review execution traces");
});

test("creates a new task", async ({ page, setupMocks }) => {
  await setupMocks();
  const tasksPage = new TasksPage(page);
  await tasksPage.goto();
  await tasksPage.expectLoaded();
  await tasksPage.createTask("Ship Playwright smoke coverage");

  await tasksPage.expectTaskVisible("Ship Playwright smoke coverage");
});

test("task appears in list after creation and completion", async ({ page, setupMocks }) => {
  await setupMocks();
  const tasksPage = new TasksPage(page);
  await tasksPage.goto();
  await tasksPage.expectLoaded();
  await tasksPage.createTask("Validate task completion");
  await tasksPage.expectTaskVisible("Validate task completion");
  await tasksPage.completeTask("Validate task completion");

  await tasksPage.expectVelocityMessage("Validate task completion");
  await expect(page.getByText(/completed/i).first()).toBeVisible();
});
