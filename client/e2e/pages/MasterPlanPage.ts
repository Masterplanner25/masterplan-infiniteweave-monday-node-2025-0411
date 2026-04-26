import { expect, type Page } from "@playwright/test";

export class MasterPlanPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/masterplan");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { name: /master plans/i })).toBeVisible();
  }

  async expectPlanVisible(versionLabel: string) {
    await expect(this.page.getByText(versionLabel)).toBeVisible();
  }

  async activatePlan() {
    await this.page.getByRole("button", { name: /^activate$/i }).first().click();
  }

  async openAnchorModal() {
    await this.page.getByRole("button", { name: /set anchor/i }).first().click();
  }

  async expectAnchorDialogVisible() {
    await expect(this.page.getByRole("heading", { name: /set anchor/i })).toBeVisible();
  }
}
