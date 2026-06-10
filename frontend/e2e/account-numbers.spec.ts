import { test, expect } from "@playwright/test";

// These tests require a live backend + database (not available in CI)
test.skip(() => !process.env.TARGET_URL, "Skipped: no backend (set TARGET_URL)");

test.describe("Account numbers in FetchUser", () => {
  test("displays account numbers when fetching user by username", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "User Utils" }).click();
    await expect(page).toHaveURL(/\/user/);

    // Scope to the Username card
    const usernameCard = page
      .locator("article")
      .filter({ hasText: "Fetch User details from users Quay.io Username" });

    await usernameCard.locator("input#user-name").fill("subscription");
    await usernameCard.getByRole("button", { name: "Fetch User" }).click();

    // Verify account numbers from marketplace API (FakeUserApi returns [12345])
    await expect(usernameCard.getByText("Account numbers")).toBeVisible({
      timeout: 10_000,
    });
    await expect(usernameCard.getByText("12345")).toBeVisible();
  });

  test("displays account numbers when fetching user by email", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "User Utils" }).click();
    await expect(page).toHaveURL(/\/user/);

    // Scope to the Email card
    const emailCard = page
      .locator("article")
      .filter({ hasText: "Fetch User details from users Quay.io Email" });

    await emailCard
      .locator("input#user-email")
      .fill("subscriptions@devtable.com");
    await emailCard.getByRole("button", { name: "Fetch User" }).click();

    // Verify account numbers from marketplace API
    await expect(emailCard.getByText("Account numbers")).toBeVisible({
      timeout: 10_000,
    });
    await expect(emailCard.getByText("12345")).toBeVisible();
  });

  test("shows error for non-existent user", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "User Utils" }).click();

    const usernameCard = page
      .locator("article")
      .filter({ hasText: "Fetch User details from users Quay.io Username" });

    await usernameCard.locator("input#user-name").fill("nonexistent_user");
    await usernameCard.getByRole("button", { name: "Fetch User" }).click();

    // Error modal appears at page level
    await expect(
      page.getByText("Could not find user nonexistent_user")
    ).toBeVisible({ timeout: 10_000 });
  });
});
