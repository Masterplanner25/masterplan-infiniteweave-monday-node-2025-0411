import { expect, test } from "./fixtures";
import { LoginPage } from "./pages/LoginPage";

async function loginAsUser(page, setupMocks) {
  await setupMocks({ isAdmin: false });
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.goto("/login");
  await new LoginPage(page).login("testuser@aindy.ai", "testpass");
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("ARM analyze page loads with default file path", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  await page.goto("/arm/analyze");

  await expect(
    page.getByRole("heading", { name: "ARM — Analyze" })
  ).toBeVisible({ timeout: 5000 });

  await expect(
    page.getByDisplayValue("tests/example.py")
  ).toBeVisible({ timeout: 3000 });

  await expect(
    page.getByRole("button", { name: "Run Analysis" })
  ).toBeVisible({ timeout: 3000 });
});

test("ARM analyze submits and displays result summary", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  await page.goto("/arm/analyze");

  await expect(
    page.getByRole("heading", { name: "ARM — Analyze" })
  ).toBeVisible({ timeout: 5000 });

  await page.getByRole("button", { name: "Run Analysis" }).click();

  await expect(
    page.getByText("Code analysis complete").first()
  ).toBeVisible({ timeout: 6000 });
});

test("ARM analyze shows error on failed analysis", async ({ page, setupMocks }) => {
  await loginAsUser(page, setupMocks);
  await page.goto("/arm/analyze");

  await expect(
    page.getByRole("heading", { name: "ARM — Analyze" })
  ).toBeVisible({ timeout: 5000 });

  const input = page.getByPlaceholder("File path (e.g. tests/example.py)");
  await input.fill("bad/path.py");
  await page.getByRole("button", { name: "Run Analysis" }).click();

  await expect(
    page.getByText(/error|not found|failed/i).first()
  ).toBeVisible({ timeout: 6000 });
});
