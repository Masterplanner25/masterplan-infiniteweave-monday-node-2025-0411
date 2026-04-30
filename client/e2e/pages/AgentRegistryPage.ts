import { expect, type Page } from "@playwright/test";

export class AgentRegistryPage {
  readonly url = "/platform/registry";

  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto(this.url);
  }

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/platform\/registry$/);
    await expect(
      this.page.getByRole("heading", { name: "Agent Federation" }),
    ).toBeVisible({ timeout: 5000 });
  }
}
