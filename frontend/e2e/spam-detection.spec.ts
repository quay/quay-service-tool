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
  original_description: string;
  review_label?: 'spam' | 'ham';
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

test('Spam Detection operator workflow covers artifacts, labels, recovery, and cleanup', async ({ page }) => {
  const dismissDescription =
    'gift card promotion https://dismiss.example This deliberately long repository description provides enough detail for an operator to review the complete classifier input without forcing every table row to remain expanded by default.';
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
      original_description: 'free casino bonus https://restore.example',
    },
    {
      uuid: 'record-cleanup',
      namespace_name: 'publicns',
      repository_name: 'spam-cleanup',
      status: 'flagged',
      classifier_score: 0.9844,
      original_description: 'crypto jackpot offer https://cleanup.example',
    },
    {
      uuid: 'record-dismiss',
      namespace_name: 'publicns',
      repository_name: 'spam-dismiss',
      status: 'flagged',
      classifier_score: 0.9733,
      original_description: dismissDescription,
    },
  ];
  const reviewActions: string[] = [];
  const auditActions: any[] = [];
  let policyPayload: any;
  let redactionPayload: any;
  let reopenPayload: any;
  let classifyPayload: any;
  let manualInspectPayload: any;
  let manualAddPayload: any;
  let artifactRequested = false;
  let artifactRequestMethod: string | undefined;
  let artifactRequestResourceType: string | undefined;
  let artifactImported = false;
  let artifactPromoted = false;
  let artifactPromoteMethod: string | undefined;

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
  await page.route('**/spam-detection/classifiers/import-artifact', async (route) => {
    artifactImported = true;
    classifiers.push({
      uuid: 'classifier-imported',
      name: 'Production classifier',
      enabled: 0,
      artifact_version: 'production-v1',
      artifact_sha256: 'sha-production-v1',
    });
    await fulfillJson(
      route,
      {
        classifier: classifiers[1],
        created: true,
        imported_artifact_version: 'production-v1',
      },
      201
    );
  });
  await page.route('**/spam-detection/classifiers/classifier-imported', async (route) => {
    classifiers.forEach((item) => {
      item.enabled = item.uuid === 'classifier-imported' ? 1 : 0;
    });
    await fulfillJson(route, { classifier: classifiers[1] });
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
  await page.route('**/spam-detection/classifiers/classifier-1/artifact', async (route) => {
    artifactRequested = true;
    artifactRequestMethod = route.request().method();
    artifactRequestResourceType = route.request().resourceType();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'content-disposition': `attachment; filename="quay-spam-classifier-${classifiers[0].artifact_version}.json"`,
      },
      body: JSON.stringify({ version: classifiers[0].artifact_version }),
    });
  });
  await page.route('**/spam-detection/classifiers/classifier-1/promote-artifact', async (route) => {
    artifactPromoted = true;
    artifactPromoteMethod = route.request().method();
    auditActions.unshift({
      created_at: '2026-07-15T01:00:00',
      namespace_name: null,
      repository_name: null,
      action: 'artifact_promote',
      from_status: null,
      to_status: null,
      operator: 'reviewer',
      details_json: {
        classifier_uuid: 'classifier-1',
        artifact_version: classifiers[0].artifact_version,
      },
    });
    await fulfillJson(route, { classifier: classifiers[0] });
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
      repos_scanned: 4,
      repos_matched: 3,
      matches: [
        {
          namespace_name: 'publicns',
          repository_name: 'spam-restore',
          visibility: 'public',
          classifier_score: 0.9912,
          description_excerpt: 'free casino bonus crypto gift cards click now https://spam.example',
        },
        {
          namespace_name: 'publicns',
          repository_name: 'spam-cleanup',
          visibility: 'public',
          classifier_score: 0.9844,
          description_excerpt: 'limited time crypto jackpot bonus https://spam.example',
        },
        {
          namespace_name: 'publicns',
          repository_name: 'spam-dismiss',
          visibility: 'public',
          classifier_score: 0.9733,
          description_excerpt: 'crypto promotion https://spam.example',
          description: dismissDescription,
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
      repos_scanned: 4,
      repos_matched: 3,
      repos_flagged: payload.dry_run ? 0 : 3,
    });
    await fulfillJson(route, { run: runs[0] }, 201);
  });
  await page.route(/.*\/spam-detection\/review(?:\?.*)?$/, async (route) => {
    const statuses = new URL(route.request().url()).searchParams.getAll('status');
    const visibleRecords = statuses.length
      ? records.filter((record) => statuses.includes(record.status))
      : records.filter((record) => ['flagged', 'quarantined'].includes(record.status));
    await fulfillJson(route, { records: visibleRecords });
  });
  await page.route('**/spam-detection/audit', async (route) => {
    await fulfillJson(route, { actions: auditActions });
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
    auditActions.unshift({
      created_at: '2026-07-15T01:00:00',
      namespace_name: record.namespace_name,
      repository_name: record.repository_name,
      action,
      from_status: record.status,
      to_status:
        action === 'quarantine'
          ? 'quarantined'
          : action === 'restore'
          ? 'restored'
          : action === 'reopen'
          ? 'flagged'
          : action === 'redact'
          ? 'redacted'
          : action === 'classify'
          ? record.status
          : 'dismissed',
      operator: 'reviewer',
      details_json: ['reopen', 'classify'].includes(action) ? route.request().postDataJSON() : {},
    });
    if (action === 'quarantine') {
      record.status = 'quarantined';
      record.review_label = 'spam';
    } else if (action === 'restore') {
      record.status = 'restored';
      record.review_label = 'ham';
    } else if (action === 'reopen') {
      reopenPayload = route.request().postDataJSON();
      record.status = 'flagged';
      delete record.review_label;
    } else if (action === 'redact') {
      redactionPayload = route.request().postDataJSON();
      record.status = 'redacted';
      record.review_label = 'spam';
    } else if (action === 'dismiss') {
      record.status = 'dismissed';
      record.review_label = 'ham';
    } else if (action === 'classify') {
      classifyPayload = route.request().postDataJSON();
      record.review_label = classifyPayload.label;
    }
    await fulfillJson(route, { record });
  });
  await page.route('**/spam-detection/review/manual/inspect', async (route) => {
    manualInspectPayload = route.request().postDataJSON();
    await fulfillJson(route, {
      repository: {
        namespace_name: 'publicns',
        repository_name: 'missed-spam',
        description: 'stream free movies and promotions https://missed.example',
        visibility: 'public',
        classifier_score: 0.0001,
        scan_threshold: 0.5,
        eligible: true,
        hard_filter_results: {
          repository_empty: { matched: true },
          visibility: { matched: true, value: 'public' },
          description_hyperlink: { matched: true },
        },
      },
    });
  });
  await page.route('**/spam-detection/review/manual', async (route) => {
    manualAddPayload = route.request().postDataJSON();
    const record: ReviewRecord = {
      uuid: 'record-manual',
      namespace_name: 'publicns',
      repository_name: 'missed-spam',
      status: 'flagged',
      classifier_score: 0.0001,
      original_description: 'stream free movies and promotions https://missed.example',
      review_label: 'spam',
    };
    records.push(record);
    auditActions.unshift({
      created_at: '2026-07-15T01:00:00',
      namespace_name: record.namespace_name,
      repository_name: record.repository_name,
      action: 'manual_flag',
      from_status: null,
      to_status: 'flagged',
      operator: 'reviewer',
      details_json: { reason: manualAddPayload.reason },
    });
    await fulfillJson(route, { record }, 201);
  });

  await openSpamDetection(page);

  await expect(page.getByRole('cell', { name: 'Default classifier' })).toBeVisible();
  await page.getByLabel('Text').fill('free casino bonus crypto gift cards click now');
  await page.getByRole('button', { name: 'Add example' }).click();
  await expect(page.getByText('Training example added')).toBeVisible();
  await closeFeedback(page);

  await page.getByRole('button', { name: 'Train new version' }).click();
  await expect(page.getByText('Artifact e2e-trained generated')).toBeVisible();
  await closeFeedback(page);
  const artifactDownloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const artifactDownload = await artifactDownloadPromise;
  expect(artifactDownload.suggestedFilename()).toBe('quay-spam-classifier-e2e-trained.json');
  await artifactDownload.path();
  await expect(page.getByText('Artifact e2e-trained download started')).toBeVisible();
  expect(artifactRequested).toBe(true);
  expect(artifactRequestMethod).toBe('GET');
  expect(artifactRequestResourceType).toBe('xhr');
  await closeFeedback(page);

  await page.getByRole('button', { name: 'Promote' }).click();
  await expect(page.getByText('Artifact e2e-trained promoted')).toBeVisible();
  expect(artifactPromoted).toBe(true);
  expect(artifactPromoteMethod).toBe('POST');
  await closeFeedback(page);

  await page.locator('#artifact-name').fill('Production classifier');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'production-v1.json',
    mimeType: 'application/json',
    buffer: Buffer.from('{"version":"production-v1"}'),
  });
  await page.getByLabel('Activate after import').uncheck();
  await page.getByRole('button', { name: 'Import', exact: true }).click();
  await expect(page.getByText('Artifact production-v1 imported')).toBeVisible();
  await closeFeedback(page);
  expect(artifactImported).toBe(true);
  const importedRow = page.getByRole('table', { name: 'Classifiers' }).locator('tr', {
    hasText: 'Production classifier',
  });
  await importedRow.getByRole('button', { name: 'Activate' }).click();
  await expect(page.getByText('Artifact production-v1 activated')).toBeVisible();
  await closeFeedback(page);
  await expect(importedRow).toContainText('Active');

  await page.getByRole('tab', { name: 'Policy' }).click();
  await expect(page.getByLabel('Quarantine description')).toHaveValue(/published support timeline/);
  await page.getByLabel('Rescan unchanged terminal review records').check();
  await page.getByLabel('Scan all repositories').check();
  await page.getByRole('button', { name: 'Save policy' }).click();
  await expect(page.getByText('Policy saved')).toBeVisible();
  expect(policyPayload.max_repos).toBe(0);
  expect(policyPayload.rescan_terminal_records).toBe(true);
  expect(policyPayload.quarantine_description).toContain('remove promotional');
  await closeFeedback(page);

  await page.getByRole('tab', { name: 'Preview' }).click();
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByText('3 matches from 4 repositories scanned')).toBeVisible();
  const previewPanel = page.getByLabel('Preview', { exact: true });
  await expect(previewPanel.locator('tr', { hasText: 'publicns/spam-restore' })).toBeVisible();
  await expect(previewPanel.locator('tr', { hasText: 'publicns/spam-cleanup' })).toBeVisible();
  await expect(previewPanel.locator('tr', { hasText: 'publicns/spam-dismiss' })).toBeVisible();
  await expect(
    previewPanel.locator('tr', { hasText: 'publicns/spam-dismiss' }).getByRole('button', { name: 'Show more' })
  ).toBeVisible();
  await expect(previewPanel.getByRole('link', { name: 'publicns/spam-restore' })).toHaveAttribute(
    'href',
    'http://localhost:8080/repository/publicns/spam-restore'
  );

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
  await page.getByRole('button', { name: 'Add missed repository' }).click();
  const manualReviewDialog = page.getByRole('dialog', { name: 'Add missed repository' });
  await manualReviewDialog.getByRole('textbox', { name: 'Namespace' }).fill('publicns');
  await manualReviewDialog.getByRole('textbox', { name: 'Repository' }).fill('missed-spam');
  await manualReviewDialog.getByRole('textbox', { name: 'Reason' }).fill('Confirmed false negative');
  await manualReviewDialog.getByRole('button', { name: 'Inspect' }).click();
  await expect(page.getByText('Score 0.0001 / threshold 0.5000')).toBeVisible();
  await expect(page.getByText('stream free movies and promotions https://missed.example')).toBeVisible();
  await manualReviewDialog.getByRole('button', { name: 'Add as spam' }).click();
  await expect(page.getByText('Repository added to review as spam')).toBeVisible();
  await closeFeedback(page);
  expect(manualInspectPayload).toEqual({ namespace: 'publicns', repository: 'missed-spam' });
  expect(manualAddPayload).toEqual({
    namespace: 'publicns',
    repository: 'missed-spam',
    reason: 'Confirmed false negative',
  });
  const manualRow = reviewPanel.locator('tr', { hasText: 'publicns/missed-spam' });
  await expect(manualRow).toContainText('spam');
  await expect(manualRow).toContainText('0.0001');
  const restoreRow = reviewPanel.locator('tr', { hasText: 'publicns/spam-restore' });
  await restoreRow.getByRole('button', { name: 'Quarantine' }).click();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('quarantine completed')).toBeVisible();
  await closeFeedback(page);
  await expect(restoreRow).toContainText('quarantined');
  await expect(restoreRow).toContainText('spam');
  await expect(restoreRow.getByRole('button', { name: 'Label spam' })).toHaveCount(0);
  await expect(restoreRow.getByRole('button', { name: 'Label ham' })).toHaveCount(0);

  const dismissRow = reviewPanel.locator('tr', { hasText: 'publicns/spam-dismiss' });
  await expect(dismissRow.getByRole('link', { name: 'publicns/spam-dismiss' })).toHaveAttribute(
    'href',
    'http://localhost:8080/repository/publicns/spam-dismiss'
  );
  const expandDescription = dismissRow.getByRole('button', { name: 'Show more' });
  await expect(expandDescription).toHaveAttribute('aria-expanded', 'false');
  await expandDescription.click();
  await expect(dismissRow.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true');
  await dismissRow.getByRole('button', { name: 'Label spam' }).click();
  await expect(page.getByText('Description to label')).toBeVisible();
  await expect(page.getByText(dismissDescription).last()).toBeVisible();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('Match labeled spam')).toBeVisible();
  await closeFeedback(page);
  expect(classifyPayload).toEqual({ label: 'spam' });
  await expect(dismissRow).toContainText('spam');
  await dismissRow.getByRole('button', { name: 'Dismiss' }).click();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('dismiss completed')).toBeVisible();
  await closeFeedback(page);
  await expect(dismissRow).toContainText('dismissed');
  await dismissRow.getByRole('button', { name: 'Reopen review' }).click();
  await page.getByLabel('Reason').fill('Dismissal was approved in error');
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('reopen completed')).toBeVisible();
  await closeFeedback(page);
  await expect(dismissRow).toContainText('flagged');
  await restoreRow.getByRole('button', { name: 'Restore' }).click();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('restore completed')).toBeVisible();
  await closeFeedback(page);
  await expect(restoreRow).toContainText('restored');
  await restoreRow.getByRole('button', { name: 'Reopen review' }).click();
  await expect(page.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  await page.getByLabel('Reason').fill('Restore was approved in error');
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('reopen completed')).toBeVisible();
  await closeFeedback(page);
  await expect(restoreRow).toContainText('flagged');
  expect(reopenPayload).toEqual({ reason: 'Restore was approved in error' });
  await restoreRow.getByRole('button', { name: 'Quarantine' }).click();
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('quarantine completed')).toBeVisible();
  await closeFeedback(page);
  await expect(restoreRow).toContainText('quarantined');

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
  await expect(cleanupRow).toHaveCount(0);
  expect(redactionPayload).toEqual({ redacted_description: '[redacted by spam cleanup]' });
  expect(reviewActions).toEqual([
    'record-restore:quarantine',
    'record-dismiss:classify',
    'record-dismiss:dismiss',
    'record-dismiss:reopen',
    'record-restore:restore',
    'record-restore:reopen',
    'record-restore:quarantine',
    'record-cleanup:quarantine',
    'record-cleanup:redact',
  ]);
  await page.getByRole('tab', { name: 'Audit' }).click();
  const auditPanel = page.getByLabel('Audit', { exact: true });
  await expect(auditPanel).toContainText('artifact_promote');
  await expect(auditPanel).toContainText('publicns/spam-cleanup');
  await expect(auditPanel.getByRole('link', { name: 'publicns/spam-cleanup' }).first()).toHaveAttribute(
    'href',
    'http://localhost:8080/repository/publicns/spam-cleanup'
  );
  await expect(auditPanel).toContainText('quarantined -> redacted');
  await expect(auditPanel).toContainText('restored -> flagged');
  await expect(auditPanel).toContainText('dismissed -> flagged');
  await expect(auditPanel).toContainText('Restore was approved in error');
});
