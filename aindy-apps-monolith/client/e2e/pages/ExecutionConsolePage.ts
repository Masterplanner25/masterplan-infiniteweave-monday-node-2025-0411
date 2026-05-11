import { expect, type Page } from "@playwright/test";

export class ExecutionConsolePage {
  readonly url = "/platform/executions";

  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto(this.url);
  }

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/platform\/executions$/);
    await expect(
      this.page.getByRole("heading", { name: "Execution Console" }),
    ).toBeVisible({ timeout: 5000 });
  }
}
