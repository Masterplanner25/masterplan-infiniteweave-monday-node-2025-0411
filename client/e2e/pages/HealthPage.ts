import { expect, type Page } from "@playwright/test";

export class HealthPage {
  readonly url = "/platform/health";
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto(this.url);
  }

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/platform\/health$/);
    await expect(this.page.getByRole("heading", { name: /system health/i })).toBeVisible({ timeout: 5000 });
  }

  async expectHealthy() {
    await expect(this.page.getByText(/uptime:/i)).toBeVisible();
    await expect(this.page.getByText(/^healthy$/i).first()).toBeVisible();
  }
}
