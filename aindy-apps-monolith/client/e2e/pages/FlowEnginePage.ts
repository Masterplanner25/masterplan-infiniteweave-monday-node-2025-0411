import { expect, type Page } from "@playwright/test";

export class FlowEnginePage {
  readonly url = "/platform/flows";
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto(this.url);
  }

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/platform\/flows$/);
    await expect(this.page.getByRole("heading", { name: "Execution Console" })).toBeVisible({ timeout: 5000 });
    await expect(this.page.getByRole("button", { name: "Flow Runs" })).toBeVisible();
  }
}
