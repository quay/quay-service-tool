import { test, expect } from "@playwright/test";

test("Spam Detection review redaction requires confirmation text", async ({
  page,
}) => {
  let redactionPayload: unknown;

  await page.route("**/banner", async (route) => {
    await route.fulfill({ json: { messages: [] } });
  });
  await page.route("**/spam-detection/classifiers", async (route) => {
    await route.fulfill({
      json: {
        classifiers: [
          {
            uuid: "classifier-1",
            name: "Default classifier",
            enabled: 1,
            artifact_version: "20260620.1",
            artifact_sha256: "abc123",
          },
        ],
      },
    });
  });
  await page.route("**/spam-detection/policy", async (route) => {
    await route.fulfill({
      json: {
        policy: {
          scan_threshold: 0.9,
          ingress_threshold: 0.9,
          include_private: 0,
          scan_dry_run: 1,
          max_repos: 100,
          batch_size: 50,
          quarantine_description: "quarantined",
        },
      },
    });
  });
  await page.route("**/spam-detection/runs", async (route) => {
    await route.fulfill({ json: { runs: [] } });
  });
  await page.route("**/spam-detection/review/record-1/redact", async (route) => {
    redactionPayload = route.request().postDataJSON();
    await route.fulfill({
      json: { record: { uuid: "record-1", status: "redacted" } },
    });
  });
  await page.route("**/spam-detection/review", async (route) => {
    await route.fulfill({
      json: {
        records: [
          {
            uuid: "record-1",
            namespace_name: "publicns",
            repository_name: "spam",
            status: "quarantined",
            classifier_score: 0.99,
          },
        ],
      },
    });
  });

  await page.goto("/");
  await expect(page.getByText(/add site banner/i)).toBeVisible();
  await page.evaluate(() => {
    window.history.pushState({}, "", "/spam-detection");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page).toHaveURL(/\/spam-detection/);
  await page.getByRole("tab", { name: "Review", exact: true }).click();
  await page.getByRole("button", { name: "Redact" }).click();

  await expect(page.getByRole("button", { name: "Confirm" })).toBeDisabled();

  await page.getByLabel("Redacted description").fill("[redacted]");
  await page.getByRole("button", { name: "Confirm" }).click();

  await expect(page.getByText("redact completed")).toBeVisible();
  expect(redactionPayload).toEqual({ redacted_description: "[redacted]" });
});
