import { expect, test as setup } from "@playwright/test";

import { setupApiMocks, VALID_EMAIL, VALID_PASSWORD } from "../fixtures";
import { LoginPage } from "../pages/LoginPage";

setup("authenticate", async ({ page }) => {
  await setupApiMocks(page);
  await page.goto("/login");

  const loginPage = new LoginPage(page);
  await loginPage.expectVisible();
  await loginPage.login(VALID_EMAIL, VALID_PASSWORD);

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("button", { name: /logout/i })).toBeVisible();
  await page.context().storageState({ path: "e2e/.auth/user.json" });
});
