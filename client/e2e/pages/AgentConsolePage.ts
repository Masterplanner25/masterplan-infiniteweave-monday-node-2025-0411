import { expect, type Page } from "@playwright/test";

export class AgentConsolePage {
  readonly url = "/platform/agent";
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto(this.url);
  }

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/platform\/agent$/);
    await expect(this.page.getByRole("heading", { name: "Agent Console" })).toBeVisible({ timeout: 5000 });
  }

  async expectRunsVisible() {
    await expect(this.page.getByText("Audit masterplan execution drift")).toBeVisible();
  }
}
