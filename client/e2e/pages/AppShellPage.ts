import { expect, type Page } from "@playwright/test";

export class AppShellPage {
  constructor(private readonly page: Page) {}

  async expectWorkspaceNavigation() {
    await expect(this.page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(this.page.getByRole("link", { name: "Tasks" })).toBeVisible();
    await expect(this.page.getByRole("link", { name: "MasterPlan" })).toBeVisible();
  }

  async goToTasks() {
    await this.page.getByRole("link", { name: "Tasks" }).click();
  }

  async goToMasterPlan() {
    await this.page.getByRole("link", { name: "MasterPlan" }).click();
  }

  async logout() {
    await this.page.getByRole("button", { name: /logout/i }).click();
  }
}
