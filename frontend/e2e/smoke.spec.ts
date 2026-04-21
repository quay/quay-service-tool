import { test, expect } from "@playwright/test";

test("app renders with header and sidebar", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header")).toBeVisible();
  await expect(page.getByRole("navigation")).toBeVisible();
});

test("Site Utils page shows Add Site Banner card", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Add Site Banner")).toBeVisible();
});

test("navigation to User Utils works", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "User Utils" }).click();
  await expect(page).toHaveURL(/\/user/);
  await expect(page.getByText("User Utils")).toBeVisible();
});

test("404 page renders for unknown routes", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    window.history.pushState({}, "", "/nonexistent");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page.getByText("404 Page not found")).toBeVisible();
  await expect(page.getByText("Take me home")).toBeVisible();
});
