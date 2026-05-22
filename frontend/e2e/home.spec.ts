import { expect, test } from "@playwright/test";

test("home page loads search console", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "SEC Research Console" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Search a public company ticker" })).toBeVisible();
});
