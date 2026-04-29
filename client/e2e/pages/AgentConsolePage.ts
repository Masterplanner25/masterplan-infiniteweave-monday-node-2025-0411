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

  async submitGoal(goal: string) {
    const input = this.page.getByPlaceholder("e.g. Find leads in the AI consulting space and create a follow-up task");
    await input.fill(goal);
    await this.page.getByRole("button", { name: "Run Agent" }).click();
  }

  async expectPendingApprovalVisible() {
    await expect(this.page.getByText(/awaiting approval/i).first()).toBeVisible({ timeout: 5000 });
  }

  async approveRun() {
    await this.page.getByRole("button", { name: "Approve" }).first().click();
    await this.page.getByText(/Validate cross-domain event propagation/i).first().click();
  }

  async openTimeline() {
    await this.page.getByRole("button", { name: /Timeline/i }).first().click();
  }

  async expectTimelineEventVisible(eventType: string) {
    await expect(this.page.getByText(eventType, { exact: false })).toBeVisible({ timeout: 5000 });
  }
}
