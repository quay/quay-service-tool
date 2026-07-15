const path = require('path');
const {execFileSync} = require('child_process');

const {chromium, expect, request} = require(
  path.join(__dirname, '../frontend/node_modules/@playwright/test'),
);

const quayUrl = process.env.QUAY_URL || 'http://localhost:8080';
const serviceToolUrl = process.env.SERVICE_TOOL_URL || 'http://localhost:9000';
const serviceToolApiUrl = process.env.SERVICE_TOOL_API_URL || 'http://localhost:5001';
const containerRuntime = process.env.CONTAINER_RUNTIME || 'podman';
const slowMo = Number(process.env.PLAYWRIGHT_SLOW_MO || 530);
const stepDelay = Number(process.env.DEMO_STEP_DELAY || 3500);
const clickDelay = Number(process.env.DEMO_CLICK_DELAY || 670);
const holdSeconds = Number(process.env.HOLD_SECONDS || 600);
const namespace = 'admin';
const legacyRepository = `legacy-spam-review-${Date.now()}`;
const spamDescription =
  'free casino bonus crypto gift cards click now https://spam.example';
const quarantineNotice = 'This repository description was removed by Quay spam detection.';
const reopenReason = 'Restore was approved in error';

async function checkedJson(response, label) {
  if (!response.ok()) {
    throw new Error(`${label}: ${response.status()} ${await response.text()}`);
  }
  return response.json();
}

async function csrf(context) {
  const response = await context.get(`${quayUrl}/csrf_token`, {
    headers: {'X-Requested-With': 'XMLHttpRequest'},
  });
  const body = await checkedJson(response, 'get Quay CSRF token');
  return body.csrf_token;
}

async function mutateQuay(context, method, route, data) {
  const token = await csrf(context);
  return context[method](`${quayUrl}${route}`, {
    headers: {'X-CSRF-Token': token},
    data,
    timeout: 15_000,
  });
}

async function prepareLegacyRepository() {
  const anonymous = await request.newContext({ignoreHTTPSErrors: true});
  try {
    const createUser = await mutateQuay(anonymous, 'post', '/api/v1/user/', {
      username: namespace,
      password: 'password',
      email: 'admin@example.com',
    });
    if (!createUser.ok()) {
      const body = await createUser.text();
      if (!/already exists|already taken/i.test(body)) {
        throw new Error(`create demo user: ${createUser.status()} ${body}`);
      }
    }
  } finally {
    await anonymous.dispose();
  }

  const authenticated = await request.newContext({ignoreHTTPSErrors: true});
  try {
    await checkedJson(
      await mutateQuay(authenticated, 'post', '/api/v1/signin', {
        username: namespace,
        password: 'password',
      }),
      'sign in demo user',
    );
    const existingDemoRepositories = execFileSync(
      containerRuntime,
      [
        'exec',
        'quay-db',
        'psql',
        '-U',
        'quay',
        '-d',
        'quay',
        '-tA',
        '-c',
        `SELECT name FROM repository WHERE namespace_user_id = (SELECT id FROM "user" WHERE username = '${namespace}') AND name LIKE 'legacy-spam-review%';`,
      ],
      {encoding: 'utf8'},
    )
      .split('\n')
      .map((name) => name.trim())
      .filter(Boolean);
    for (const repository of existingDemoRepositories) {
      await mutateQuay(
        authenticated,
        'delete',
        `/api/v1/repository/${namespace}/${repository}`,
      ).catch(() => {});
    }
    await checkedJson(
      await mutateQuay(authenticated, 'post', '/api/v1/repository', {
        repo_kind: 'image',
        namespace,
        visibility: 'public',
        repository: legacyRepository,
        description: 'legacy repository awaiting review',
      }),
      'create legacy demo repository',
    );
  } finally {
    await authenticated.dispose();
  }

  const sql = `
    UPDATE repository
    SET description = '${spamDescription}'
    WHERE name = '${legacyRepository}'
      AND namespace_user_id = (
        SELECT id FROM "user" WHERE username = '${namespace}'
      );
  `;
  execFileSync(
    containerRuntime,
    ['exec', 'quay-db', 'psql', '-U', 'quay', '-d', 'quay', '-v', 'ON_ERROR_STOP=1', '-c', sql],
    {stdio: 'inherit'},
  );
}

async function prepareServiceToolClassifier() {
  const api = await request.newContext({baseURL: serviceToolApiUrl});
  try {
    const classifier = (
      await checkedJson(
        await api.post('/spam-detection/classifiers', {
          data: {
            name: `Reviewer demo ${Date.now()}`,
            enabled: true,
            scan_threshold: 0.5,
            ingress_threshold: 0.9,
          },
        }),
        'create service-tool demo classifier',
      )
    ).classifier;

    const spamExamples = [
      spamDescription,
      'casino jackpot bonus claim crypto prize',
      'free gift cards click now limited offer',
      'crypto casino promotion instant jackpot',
      'claim bonus reward click promotional link',
      'online casino free spins jackpot winner',
      'limited time crypto giveaway claim now',
      'bonus gift card promotion click here',
      'casino betting jackpot reward offer',
      'free crypto prize urgent claim link',
    ];
    const hamExamples = [
      'trusted base image for python applications',
      'container image documentation and examples',
      'production operator image for kubernetes',
      'linux distribution package repository',
      'application runtime container build',
      'database backup utility image',
      'continuous integration build tools',
      'web server container image',
      'observability collector release image',
      'open source command line utility',
    ];

    for (const text of spamExamples) {
      await checkedJson(
        await api.post(`/spam-detection/classifiers/${classifier.uuid}/training-examples`, {
          data: {text, label: 'spam', source: 'reviewer_demo'},
        }),
        'add spam training example',
      );
    }
    for (const text of hamExamples) {
      await checkedJson(
        await api.post(`/spam-detection/classifiers/${classifier.uuid}/training-examples`, {
          data: {text, label: 'ham', source: 'reviewer_demo'},
        }),
        'add ham training example',
      );
    }

    await checkedJson(
      await api.post(`/spam-detection/classifiers/${classifier.uuid}/train`, {
        data: {artifact_version: `reviewer-demo-${Date.now()}`},
      }),
      'train service-tool demo classifier',
    );
    await checkedJson(
      await api.put('/spam-detection/policy', {
        data: {
          active_classifier_uuid: classifier.uuid,
          scan_threshold: 0.5,
          scan_dry_run: false,
          include_private: false,
          max_repos: 1000,
        },
      }),
      'activate service-tool demo policy',
    );
    return classifier.name;
  } finally {
    await api.dispose();
  }
}

async function pause(label) {
  console.log(`Demo: ${label}`);
  await new Promise((resolve) => setTimeout(resolve, stepDelay));
}

async function highlightTarget(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  await locator.evaluate((element, duration) => {
    document.getElementById('spam-demo-click-marker')?.remove();
    const rect = element.getBoundingClientRect();
    const marker = document.createElement('div');
    marker.id = 'spam-demo-click-marker';
    Object.assign(marker.style, {
      position: 'fixed',
      left: `${rect.left + rect.width / 2 - 18}px`,
      top: `${rect.top + rect.height / 2 - 18}px`,
      width: '36px',
      height: '36px',
      border: '4px solid #f0ab00',
      borderRadius: '9999px',
      boxShadow: '0 0 0 5px rgba(240, 171, 0, 0.35)',
      pointerEvents: 'none',
      zIndex: '2147483647',
    });
    document.body.appendChild(marker);
    marker.animate(
      [
        {transform: 'scale(0.55)', opacity: 0},
        {transform: 'scale(1)', opacity: 1},
        {transform: 'scale(1.25)', opacity: 0.8},
      ],
      {duration: duration * 2, easing: 'ease-out'},
    );
    element.animate(
      [
        {outline: '0 solid rgba(240, 171, 0, 0)'},
        {outline: '4px solid #f0ab00', outlineOffset: '4px'},
        {outline: '0 solid rgba(240, 171, 0, 0)', outlineOffset: '8px'},
      ],
      {duration: duration * 2, easing: 'ease-out'},
    );
    window.setTimeout(() => marker.remove(), duration * 2);
  }, clickDelay);
  await page.waitForTimeout(clickDelay);
}

async function clickForDemo(page, locator) {
  await highlightTarget(page, locator);
  await locator.click();
  await page.waitForTimeout(clickDelay);
}

async function fillForDemo(page, locator, value) {
  await highlightTarget(page, locator);
  await locator.click();
  await locator.fill(value);
  await page.waitForTimeout(clickDelay);
}

async function closeFeedback(page) {
  const close = page.getByRole('button', {name: 'Close'});
  if (await close.isVisible()) {
    await clickForDemo(page, close);
  }
}

async function runVisibleDemo(classifierName) {
  const browser = await chromium.launch({channel: 'chrome', headless: false, slowMo});
  const context = await browser.newContext();
  const quayPage = await context.newPage();
  const serviceToolPage = await context.newPage();

  try {
    await quayPage.goto(`${quayUrl}/react`, {waitUntil: 'domcontentloaded'});
    await quayPage.goto(`${quayUrl}/signin`, {waitUntil: 'domcontentloaded'});
    await expect(quayPage.getByText('Log in to your account')).toBeVisible({timeout: 20_000});
    await fillForDemo(quayPage, quayPage.getByRole('textbox', {name: /username/i}), namespace);
    await fillForDemo(quayPage, quayPage.getByLabel(/password/i), 'password');
    await clickForDemo(quayPage, quayPage.locator('button[type="submit"]'));
    await expect(quayPage).not.toHaveURL(/\/signin/, {timeout: 20_000});

    await quayPage.goto(`${quayUrl}/repository`);
    await expect(quayPage.getByRole('heading', {name: 'Repositories'})).toBeVisible({timeout: 20_000});
    await clickForDemo(quayPage, quayPage.getByRole('button', {name: 'Create Repository'}));
    await fillForDemo(
      quayPage,
      quayPage.getByTestId('repository-name-input'),
      `blocked-spam-${Date.now()}`,
    );
    await fillForDemo(quayPage, quayPage.getByTestId('repository-description-input'), spamDescription);
    const rejectedResponse = quayPage.waitForResponse(
      (response) =>
        response.url().endsWith('/api/v1/repository') &&
        response.request().method() === 'POST',
    );
    await clickForDemo(quayPage, quayPage.getByTestId('create-repository-submit-btn'));
    expect((await rejectedResponse).status()).toBe(400);
    await expect(quayPage.getByText(/Repository description was rejected by spam detection/)).toBeVisible();
    await pause('Quay visibly rejected the spam repository description');
    await quayPage.keyboard.press('Escape');

    await quayPage.goto(`${quayUrl}/repository/${namespace}/${legacyRepository}`);
    await expect(quayPage.getByText(spamDescription)).toBeVisible({timeout: 20_000});
    await pause('Quay shows a synthetic legacy spam repository that predates ingress enforcement');

    await clickForDemo(quayPage, quayPage.getByRole('button', {name: 'Edit description'}));
    await fillForDemo(
      quayPage,
      quayPage.getByRole('textbox', {name: 'Repository description'}),
      `${spamDescription} updated`,
    );
    const rejectedUpdateResponse = quayPage.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/repository/${namespace}/${legacyRepository}`) &&
        response.request().method() === 'PUT',
    );
    await clickForDemo(quayPage, quayPage.getByRole('button', {name: 'Save'}));
    expect((await rejectedUpdateResponse).status()).toBe(400);
    await expect(quayPage.getByText('Failed to update repository description')).toBeVisible();
    await pause('Quay visibly rejected a spam update and preserved the existing description');
    await clickForDemo(quayPage, quayPage.getByRole('button', {name: 'Cancel'}));
    await expect(quayPage.getByText(spamDescription)).toBeVisible();

    await serviceToolPage.goto(serviceToolUrl, {waitUntil: 'domcontentloaded'});
    await expect(serviceToolPage.getByText(/add site banner/i)).toBeVisible({timeout: 20_000});
    await serviceToolPage.evaluate(() => {
      window.history.pushState({}, '', '/spam-detection');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect(serviceToolPage).toHaveURL(/\/spam-detection/);
    await expect(serviceToolPage.getByText(classifierName)).toBeVisible({timeout: 20_000});
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('tab', {name: 'Preview'}));
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('button', {name: 'Preview'}));
    const previewPanel = serviceToolPage.getByLabel('Preview', {exact: true});
    const previewRow = previewPanel.locator('tr', {
      hasText: `${namespace}/${legacyRepository}`,
    });
    await expect(previewRow).toBeVisible({timeout: 20_000});
    await pause('Service-tool preview identifies the legacy empty repository');

    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('tab', {name: 'Runs'}));
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('button', {name: 'Run review scan'}));
    await expect(serviceToolPage.getByText('Scan completed')).toBeVisible({timeout: 30_000});
    await pause('Service-tool scan creates a flagged review record');
    await closeFeedback(serviceToolPage);

    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('tab', {name: 'Review', exact: true}));
    const reviewPanel = serviceToolPage.getByLabel('Review', {exact: true});
    const reviewRow = reviewPanel.locator('tr', {
      hasText: `${namespace}/${legacyRepository}`,
    });
    await expect(reviewRow).toContainText('flagged');
    await clickForDemo(serviceToolPage, reviewRow.getByRole('button', {name: 'Quarantine'}));
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('button', {name: 'Confirm'}));
    await expect(serviceToolPage.getByText('quarantine completed')).toBeVisible({timeout: 20_000});
    await pause('Operator quarantines the repository from the review queue');
    await closeFeedback(serviceToolPage);

    await quayPage.bringToFront();
    await quayPage.reload();
    await expect(quayPage.getByText(new RegExp(quarantineNotice))).toBeVisible({timeout: 20_000});
    await pause('Quay now shows the repository-owner quarantine notice');

    await serviceToolPage.bringToFront();
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('tab', {name: 'Review', exact: true}));
    await expect(reviewRow).toContainText('quarantined');
    await clickForDemo(serviceToolPage, reviewRow.getByRole('button', {name: 'Restore'}));
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('button', {name: 'Confirm'}));
    await expect(serviceToolPage.getByText('restore completed')).toBeVisible({
      timeout: 20_000,
    });
    await pause('Operator restores the repository after review');
    await closeFeedback(serviceToolPage);

    await quayPage.bringToFront();
    await quayPage.reload();
    await expect(quayPage.getByText(spamDescription)).toBeVisible({
      timeout: 20_000,
    });
    await pause('Quay shows the restored spam description');

    await serviceToolPage.bringToFront();
    await expect(reviewRow).toContainText('restored');
    await clickForDemo(serviceToolPage, reviewRow.getByRole('button', {name: 'Reopen review'}));
    await fillForDemo(serviceToolPage, serviceToolPage.getByLabel('Reason'), reopenReason);
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('button', {name: 'Confirm'}));
    await expect(serviceToolPage.getByText('reopen completed')).toBeVisible({
      timeout: 20_000,
    });
    await pause('Operator reopens the mistaken restore with an audit reason');
    await closeFeedback(serviceToolPage);

    await expect(reviewRow).toContainText('flagged');
    await clickForDemo(serviceToolPage, reviewRow.getByRole('button', {name: 'Quarantine'}));
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('button', {name: 'Confirm'}));
    await expect(serviceToolPage.getByText('quarantine completed')).toBeVisible({timeout: 20_000});
    await pause('Operator quarantines the reopened repository again');
    await closeFeedback(serviceToolPage);

    await quayPage.bringToFront();
    await quayPage.reload();
    await expect(quayPage.getByText(new RegExp(quarantineNotice))).toBeVisible({
      timeout: 20_000,
    });
    await pause('Quay shows the quarantine notice after the correction');

    await serviceToolPage.bringToFront();
    await clickForDemo(serviceToolPage, serviceToolPage.getByRole('tab', {name: 'Audit'}));
    const auditPanel = serviceToolPage.getByLabel('Audit', {exact: true});
    const auditRows = auditPanel.locator('tr', {
      hasText: `${namespace}/${legacyRepository}`,
    });
    await expect(auditRows.filter({hasText: 'restored -> flagged'}).first()).toContainText(reopenReason);
    await expect(auditRows.filter({hasText: 'quarantined -> restored'}).first()).toContainText('restore');
    await expect(auditRows.filter({hasText: 'flagged -> quarantined'})).toHaveCount(2);
    await pause('Audit history records restore, reopen, and both quarantine decisions');

    console.log(`Opened ${quayUrl} and ${serviceToolUrl}/spam-detection`);
    console.log(`Keeping browser open for ${holdSeconds} seconds. Press Ctrl-C to stop earlier.`);
    await new Promise((resolve) => setTimeout(resolve, holdSeconds * 1000));
  } finally {
    await browser.close();
  }
}

(async () => {
  await prepareLegacyRepository();
  const classifierName = await prepareServiceToolClassifier();
  await runVisibleDemo(classifierName);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
