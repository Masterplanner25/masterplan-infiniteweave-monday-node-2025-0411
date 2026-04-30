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

test("freelance dashboard displays order list", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  await page.goto("/freelance");
  await expect(page.getByText("Recent Stream").first()).toBeVisible({ timeout: 5000 });
  await expect(page.getByText("Website redesign")).toBeVisible({ timeout: 5000 });
  await expect(page.getByText("Mobile app MVP")).toBeVisible({ timeout: 5000 });
});

test("freelance dashboard shows delivered order count", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  await page.goto("/freelance");
  const deliveredCard = page
    .locator("div")
    .filter({ has: page.getByText(/^Delivered$/) })
    .filter({ has: page.getByText(/^1$/) })
    .first();
  await expect(deliveredCard).toBeVisible({ timeout: 5000 });
});
