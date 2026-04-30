import { expect, type Page } from "@playwright/test";

export class GenesisPage {
  readonly url = "/genesis";
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto(this.url);
  }

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/genesis$/);
    await expect(this.page.getByRole("heading", { name: /project genesis/i })).toBeVisible({
      timeout: 5000,
    });
  }

  async startSession() {
    await this.page.getByRole("button", { name: "INITIALIZE" }).click();
  }

  async expectSessionActive() {
    await expect(this.page.getByPlaceholder("Transmitting signal...")).toBeVisible({
      timeout: 5000,
    });
  }

  async sendMessage(text: string) {
    await this.page.getByPlaceholder("Transmitting signal...").fill(text);
    await this.page.getByRole("button", { name: "SEND" }).click();
  }

  async expectResponseVisible() {
    await expect(
      this.page.getByText("I understand your goals. Let me ask — what does success look like in 3 years?"),
    ).toBeVisible({ timeout: 6000 });
  }

  async synthesize() {
    await this.page.getByRole("button", { name: "SYNTHESIZE" }).click();
  }

  async expectDraftVisible() {
    await expect(this.page.getByText("DRAFT MASTERPLAN", { exact: true })).toBeVisible({
      timeout: 6000,
    });
    await expect(this.page.getByText(/Strategic expansion/).first()).toBeVisible({ timeout: 6000 });
  }

  async lockPlan() {
    await this.page.getByRole("button", { name: "LOCK PLAN" }).click();
  }

  async expectPlanLocked() {
    await expect(this.page.getByText("MASTERPLAN LOCKED")).toBeVisible({ timeout: 6000 });
    await expect(this.page.getByText(/V5 LOCKED ARC/).first()).toBeVisible({ timeout: 6000 });
  }
}
