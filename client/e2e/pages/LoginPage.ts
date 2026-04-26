import { expect, type Page } from "@playwright/test";

export class LoginPage {
  constructor(private readonly page: Page) {}

  async goto(path = "/login") {
    await this.page.goto(path);
  }

  async login(email: string, password: string) {
    await this.page.getByLabel(/email/i).fill(email);
    await this.page.getByLabel(/password/i).fill(password);
    await this.page.getByRole("button", { name: /login and boot|booting/i }).click();
  }

  async expectVisible() {
    await expect(this.page.getByRole("heading", { name: /activate a\.i\.n\.d\.y\./i })).toBeVisible();
  }

  async expectError(message: string | RegExp) {
    await expect(this.page.getByText(message)).toBeVisible();
  }
}
