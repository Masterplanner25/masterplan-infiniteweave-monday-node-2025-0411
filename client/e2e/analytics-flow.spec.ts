import { expect, test } from "./fixtures";
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

test("dashboard KPI panel displays and recalculates the master score", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  await page.goto("/dashboard");

  await expect(page.getByRole("heading", { name: "Infinity Score" })).toBeVisible({ timeout: 5000 });
  await expect(page.getByText("82.5", { exact: true }).first()).toBeVisible({ timeout: 5000 });

  await page.getByRole("button", { name: "Recalculate" }).click();
  await expect(page.getByText("88.0", { exact: true }).first()).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/high confidence/i)).toBeVisible({ timeout: 5000 });
});
