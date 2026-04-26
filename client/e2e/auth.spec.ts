import { test, expect, VALID_EMAIL, VALID_PASSWORD } from "./fixtures";
import { LoginPage } from "./pages/LoginPage";
import { AppShellPage } from "./pages/AppShellPage";

test("redirects unauthenticated users to login", async ({ page, setupMocks }) => {
  await setupMocks();
  await page.goto("/tasks");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: /activate a\.i\.n\.d\.y\./i })).toBeVisible();
});

test("logs in with valid credentials and boots the workspace shell", async ({ page, setupMocks }) => {
  await setupMocks();
  await page.goto("/login");

  const loginPage = new LoginPage(page);
  await loginPage.login(VALID_EMAIL, VALID_PASSWORD);

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("button", { name: /logout/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tasks" })).toBeVisible();
});

test("shows error on invalid credentials", async ({ page, setupMocks }) => {
  await setupMocks();
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login("wrong@aindy.ai", "badpass");

  await loginPage.expectError(/invalid credentials/i);
  await expect(page).toHaveURL(/\/login$/);
});

test("logout clears session and redirects to login", async ({ page, setupMocks }) => {
  await setupMocks();
  await page.goto("/login");

  const loginPage = new LoginPage(page);
  await loginPage.login(VALID_EMAIL, VALID_PASSWORD);
  await expect(page).toHaveURL(/\/dashboard$/);

  const shell = new AppShellPage(page);
  await shell.logout();

  await expect(page).toHaveURL(/\/login$/);
  await expect
    .poll(async () => page.evaluate(() => localStorage.getItem("token")))
    .toBeNull();
});
