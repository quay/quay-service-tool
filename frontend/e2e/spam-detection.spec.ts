import { expect, Page, Route, test } from '@playwright/test';

type Classifier = {
  uuid: string;
  name: string;
  enabled: number;
  artifact_version: string;
  artifact_sha256: string;
};

type ReviewRecord = {
  uuid: string;
  namespace_name: string;
  repository_name: string;
  status: string;
  classifier_score: number;
};

const quarantineNotice =
  "This repository description was removed by Quay spam detection. To request restoration, contact Quay support with the namespace and repository name. Before requesting restore, remove promotional, deceptive, or unrelated link content. Restore requests are reviewed within the deployment's published support timeline.";

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({ status, json });
}

async function closeFeedback(page: Page) {
  const closeButton = page.getByRole('button', { name: 'Close' });
  if (await closeButton.isVisible()) {
    await closeButton.click();
  }
}

async function openSpamDetection(page: Page) {
  await page.goto('/');
  await expect(page.getByText(/add site banner/i)).toBeVisible();
  await page.evaluate(() => {
    window.history.pushState({}, '', '/spam-detection');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/spam-detection/);
}

test('Spam Detection operator workflow covers export, scans, restore, and cleanup', async ({ page }) => {
  const classifiers: Classifier[] = [
    {
      uuid: 'classifier-1',
      name: 'Default classifier',
      enabled: 1,
      artifact_version: 'e2e-v1',
      artifact_sha256: 'sha-before-export',
    },
  ];
  const policy = {
    scan_threshold: 0.9,
    ingress_threshold: 0.9,
    include_private: 0,
    scan_dry_run: 1,
    rescan_terminal_records: 0,
    max_repos: 100,
    batch_size: 50,
    quarantine_description: quarantineNotice,
  };
  const runs: any[] = [];
  const records: ReviewRecord[] = [
    {
      uuid: 'record-restore',
      namespace_name: 'publicns',
      repository_name: 'spam-restore',
      status: 'flagged',
      classifier_score: 0.9912,
    },
    {
      uuid: 'record-cleanup',
      namespace_name: 'publicns',
      repository_name: 'spam-cleanup',
      status: 'flagged',
      classifier_score: 0.9844,
    },
  ];
  const reviewActions: string[] = [];
  let exportPayload: any;
  let policyPayload: any;
  let redactionPayload: any;

  await page.route('**/banner', async (route) => {
    await fulfillJson(route, { messages: [] });
  });
  await page.route('**/spam-detection/classifiers', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { classifiers });
      return;
    }
    await fulfillJson(route, { classifier: classifiers[0] }, 201);
  });
  await page.route('**/spam-detection/classifiers/classifier-1/training-examples', async (route) => {
    await fulfillJson(route, { training_example: { uuid: 'example-1', ...route.request().postDataJSON() } }, 201);
  });
  await page.route('**/spam-detection/classifiers/classifier-1/train', async (route) => {
    classifiers[0] = {
      ...classifiers[0],
      artifact_version: 'e2e-trained',
      artifact_sha256: 'sha-trained',
    };
    await fulfillJson(route, { classifier: classifiers[0] });
  });
  await page.route('**/spam-detection/classifiers/classifier-1/export-artifact', async (route) => {
    exportPayload = route.request().postDataJSON();
    classifiers[0] = {
      ...classifiers[0],
      artifact_version: 'e2e-v1',
      artifact_sha256: 'sha-exported',
    };
    await fulfillJson(route, {
      classifier: {
        ...classifiers[0],
        export_path: exportPayload.output_path,
        export_sha256: 'sha-exported',
      },
    });
  });
  await page.route('**/spam-detection/policy', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { policy });
      return;
    }
    policyPayload = route.request().postDataJSON();
    Object.assign(policy, policyPayload);
    await fulfillJson(route, { policy });
  });
  await page.route('**/spam-detection/preview', async (route) => {
    await fulfillJson(route, {
      repos_scanned: 3,
      repos_matched: 2,
      matches: [
        {
          namespace_name: 'publicns',
          repository_name: 'spam-restore',
          visibility: 'public',
          classifier_score: 0.9912,
          description_excerpt: 'free casino bonus crypto gift cards click now',
        },
        {
          namespace_name: 'publicns',
          repository_name: 'spam-cleanup',
          visibility: 'public',
          classifier_score: 0.9844,
          description_excerpt: 'limited time crypto jackpot bonus',
        },
      ],
    });
  });
  await page.route('**/spam-detection/runs', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { runs });
      return;
    }
    const payload = route.request().postDataJSON();
    runs.unshift({
      uuid: payload.dry_run ? 'run-dry' : 'run-review',
      status: 'completed',
      dry_run: payload.dry_run ? 1 : 0,
      repos_scanned: 3,
      repos_matched: 2,
      repos_flagged: payload.dry_run ? 0 : 2,
    });
    await fulfillJson(route, { run: runs[0] }, 201);
  });
  await page.route('**/spam-detection/review', async (route) => {
    await fulfillJson(route, { records });
  });
  await page.route(/.*\/spam-detection\/review\/([^/]+)\/([^/]+)$/, async (route) => {
    const [, recordUuid, action] =
      route
        .request()
        .url()
        .match(/review\/([^/]+)\/([^/]+)$/) || [];
    const record = records.find((item) => item.uuid === recordUuid);
    if (!record) {
      await fulfillJson(route, { message: 'record not found' }, 404);
      return;
    }
    reviewActions.push(`${recordUuid}:${action}`);
    if (action === 'quarantine') {
      record.status = 'quarantined';
    } else if (action === 'restore') {
      record.status = 'restored';
    } else if (action === 'redact') {
      redactionPayload = route.request().postDataJSON();
      record.status = 'redacted';
    } else if (action === 'dismiss') {
      record.status = 'dismissed';
    }
    await fulfillJson(route, { record });
  });

  await openSpamDetection(page);

  await expect(page.getByText('Default classifier')).toBeVisible();
  await page.getByLabel('Text').fill('free casino bonus crypto gift cards click now');
  await page.getByRole('button', { name: 'Add example' }).click();
  await expect(page.getByText('Training example added')).toBeVisible();
  await closeFeedback(page);

  await page.getByRole('button', { name: 'Train artifact' }).click();
  await expect(page.getByText('Artifact e2e-trained generated')).toBeVisible();
  await closeFeedback(page);
  await page
    .getByLabel('Build output path')
    .fill('/private/tmp/quay-image-context/conf/spam-detection/classifier.json');
  await page.getByRole('button', { name: 'Export artifact' }).click();
  await expect(
    page.getByText('Artifact e2e-v1 exported to /private/tmp/quay-image-context/conf/spam-detection/classifier.json')
  ).toBeVisible();
  expect(exportPayload).toEqual({
    output_path: '/private/tmp/quay-image-context/conf/spam-detection/classifier.json',
  });
  await closeFeedback(page);

  await page.getByRole('tab', { name: 'Policy' }).click();
  await expect(page.getByLabel('Quarantine description')).toHaveValue(/published support timeline/);
  await page.getByLabel('Rescan unchanged terminal review records').check();
  await page.getByLabel('Max repositories').fill('25');
  await page.getByRole('button', { name: 'Save policy' }).click();
  await expect(page.getByText('Policy saved')).toBeVisible();
  expect(policyPayload.max_repos).toBe(25);
  expect(policyPayload.rescan_terminal_records).toBe(true);
  expect(policyPayload.quarantine_description).toContain('remove promotional');
  await closeFeedback(page);

  await page.getByRole('tab', { name: 'Preview' }).click();
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByText('2 matches from 3 repositories scanned')).toBeVisible();
  const previewPanel = page.getByLabel('Preview', { exact: true });
  await expect(previewPanel.locator('tr', { hasText: 'publicns/spam-restore' })).toBeVisible();
  await expect(previewPanel.locator('tr', { hasText: 'publicns/spam-cleanup' })).toBeVisible();

  await page.getByRole('tab', { name: 'Runs' }).click();
  await page.getByRole('button', { name: 'Run dry scan' }).click();
  await expect(page.getByText('Scan completed')).toBeVisible();
  await closeFeedback(page);
  await page.getByRole('button', { name: 'Run review scan' }).click();
  await expect(page.getByText('Scan completed')).toBeVisible();
  await closeFeedback(page);
  await expect(page.getByText('run-dry')).toBeVisible();
  await expect(page.getByText('run-review')).toBeVisible();

  await page.getByRole('tab', { name: 'Review', exact: true }).click();
  const reviewPanel = page.getByLabel('Review', { exact: true });
  const restoreRow = reviewPanel.locator('tr', { hasText: 'publicns/spam-restore' });
  await restoreRow.getByRole('button', { name: 'Quarantine' }).click();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('quarantine completed')).toBeVisible();
  await closeFeedback(page);
  await expect(restoreRow).toContainText('quarantined');
  await restoreRow.getByRole('button', { name: 'Restore' }).click();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('restore completed')).toBeVisible();
  await closeFeedback(page);
  await expect(restoreRow).toContainText('restored');

  const cleanupRow = reviewPanel.locator('tr', { hasText: 'publicns/spam-cleanup' });
  await cleanupRow.getByRole('button', { name: 'Quarantine' }).click();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('quarantine completed')).toBeVisible();
  await closeFeedback(page);
  await cleanupRow.getByRole('button', { name: 'Redact' }).click();
  await expect(page.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  await page.getByLabel('Redacted description').fill('[redacted by spam cleanup]');
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('redact completed')).toBeVisible();
  await closeFeedback(page);
  await expect(cleanupRow).toContainText('redacted');
  expect(redactionPayload).toEqual({ redacted_description: '[redacted by spam cleanup]' });
  expect(reviewActions).toEqual([
    'record-restore:quarantine',
    'record-restore:restore',
    'record-cleanup:quarantine',
    'record-cleanup:redact',
  ]);
});
