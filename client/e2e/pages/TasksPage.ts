import { expect, type Page } from "@playwright/test";

export class TasksPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/tasks");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { name: /execution engine/i })).toBeVisible();
  }

  async createTask(taskName: string) {
    await this.page.getByPlaceholder(/initialize new directive/i).fill(taskName);
    await this.page.getByRole("button", { name: /^add$/i }).click();
  }

  async expectTaskVisible(taskName: string) {
    await expect(this.page.getByText(taskName)).toBeVisible();
  }

  async startTask(taskName: string) {
    await expect(this.page.getByText(taskName)).toBeVisible();
    await this.page.getByRole("button", { name: /start/i }).first().click();
  }

  async completeTask(taskName: string) {
    await expect(this.page.getByText(taskName)).toBeVisible();
    await this.page.getByRole("button", { name: /done/i }).first().click();
  }

  async expectVelocityMessage(taskName: string) {
    await expect(this.page.getByText(/twr score/i)).toBeVisible();
  }
}
