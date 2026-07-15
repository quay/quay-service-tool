#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_TOOL_DIR="${SERVICE_TOOL_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

QUAY_DIR="${QUAY_DIR:-${SERVICE_TOOL_DIR}/../quay}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-${DOCKER:-podman}}"
QUAY_COMPOSE_PROJECT_NAME="${QUAY_COMPOSE_PROJECT_NAME:-}"
QUAY_URL="${QUAY_URL:-http://localhost:8080}"
SERVICE_TOOL_URL="${SERVICE_TOOL_URL:-http://localhost:9000}"
SERVICE_TOOL_API_PORT="${SERVICE_TOOL_API_PORT:-5001}"
SERVICE_TOOL_CLIENT_PORT="${SERVICE_TOOL_CLIENT_PORT:-9000}"
SERVICE_TOOL_API_URL="${SERVICE_TOOL_API_URL:-http://localhost:${SERVICE_TOOL_API_PORT}}"
QUAY_NETWORK_NAME="${QUAY_NETWORK_NAME:-}"
PLAYWRIGHT_SLOW_MO="${PLAYWRIGHT_SLOW_MO:-500}"
HOLD_SECONDS="${HOLD_SECONDS:-600}"

usage() {
  cat <<USAGE
Usage:
  make spam-demo-check
  make spam-demo
  make spam-demo-status
  make spam-demo-down
  make spam-demo-clean

Advanced usage:
  ./scripts/spam-ingress-local-demo.sh up
  ./scripts/spam-ingress-local-demo.sh test
  ./scripts/spam-ingress-local-demo.sh service-tool
  ./scripts/spam-ingress-local-demo.sh browse

Commands:
  check         Verify required local paths and commands.
  up            Start local Quay from the ingress PR worktree.
  test          Run a real Quay spam ingress API smoke test.
  service-tool  Start quay-service-tool against the same live Quay DB.
  browse        Open Quay and service-tool in system Chrome via Playwright.
  demo          Run up, test, service-tool, then browse.
  status        Show compose status for both stacks.
  down          Stop both stacks, preserving volumes.
  clean         Stop both stacks and remove compose volumes.

Environment overrides:
  QUAY_DIR=/path/to/quay-pr-worktree
  SERVICE_TOOL_DIR=/path/to/quay-service-tool (defaults to this checkout)
  CONTAINER_RUNTIME=podman|docker
  QUAY_COMPOSE_PROJECT_NAME=optional-compose-project-name
  QUAY_URL=http://localhost:8080
  SERVICE_TOOL_URL=http://localhost:9000
  SERVICE_TOOL_API_PORT=5001
  SERVICE_TOOL_CLIENT_PORT=9000
  QUAY_NETWORK_NAME=quay_default
  PLAYWRIGHT_SLOW_MO=500
  HOLD_SECONDS=600
USAGE
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

check_paths() {
  test -d "$QUAY_DIR" || {
    printf 'Quay directory not found: %s\n' "$QUAY_DIR" >&2
    exit 1
  }
  test -d "$SERVICE_TOOL_DIR" || {
    printf 'service-tool directory not found: %s\n' "$SERVICE_TOOL_DIR" >&2
    exit 1
  }
  test -f "$QUAY_DIR/local-dev/stack/config.yaml" || {
    printf 'Missing Quay local config: %s/local-dev/stack/config.yaml\n' "$QUAY_DIR" >&2
    exit 1
  }
  test -f "$QUAY_DIR/local-dev/stack/spam-classifier-e2e-v1.json" || {
    printf 'Missing Quay e2e classifier artifact: %s/local-dev/stack/spam-classifier-e2e-v1.json\n' "$QUAY_DIR" >&2
    exit 1
  }
  test -f "$SERVICE_TOOL_DIR/docker-compose.yml" || {
    printf 'Missing service-tool compose file: %s/docker-compose.yml\n' "$SERVICE_TOOL_DIR" >&2
    exit 1
  }
  test -f "$SERVICE_TOOL_DIR/frontend/playwright.config.ts" || {
    printf 'Missing service-tool Playwright config: %s/frontend/playwright.config.ts\n' "$SERVICE_TOOL_DIR" >&2
    exit 1
  }
}

check_commands() {
  require_command "$CONTAINER_RUNTIME"
  require_command make
  require_command curl
  require_command corepack
  require_command node

  runtime_available || {
    printf 'Container runtime is installed but not reachable: %s\n' "$CONTAINER_RUNTIME" >&2
    if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
      printf 'Turn on Podman, then rerun this command.\n' >&2
    fi
    exit 1
  }
}

runtime_available() {
  "$CONTAINER_RUNTIME" info >/dev/null 2>&1
}

quay_compose() {
  (
    cd "$QUAY_DIR"
    if [[ -n "$QUAY_COMPOSE_PROJECT_NAME" ]]; then
      COMPOSE_PROJECT_NAME="$QUAY_COMPOSE_PROJECT_NAME" "$CONTAINER_RUNTIME" compose "$@"
    else
      "$CONTAINER_RUNTIME" compose "$@"
    fi
  )
}

check_config() {
  grep -q 'FEATURE_SPAM_DETECTION: true' "$QUAY_DIR/local-dev/stack/config.yaml" || {
    printf 'Quay config does not enable FEATURE_SPAM_DETECTION.\n' >&2
    exit 1
  }
  grep -q 'SPAM_DETECTION_DRY_RUN: false' "$QUAY_DIR/local-dev/stack/config.yaml" || {
    printf 'Quay config does not disable SPAM_DETECTION_DRY_RUN.\n' >&2
    exit 1
  }
  grep -q 'SPAM_DETECTION_FAIL_OPEN: false' "$QUAY_DIR/local-dev/stack/config.yaml" || {
    printf 'Quay config does not set SPAM_DETECTION_FAIL_OPEN: false.\n' >&2
    exit 1
  }
}

check_all() {
  check_paths
  check_commands
  check_config
  log "Checks passed"
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local timeout="${3:-180}"
  local elapsed=0

  log "Waiting for ${label}: ${url}"
  until curl -fsS "$url" >/dev/null 2>&1; do
    if (( elapsed >= timeout )); then
      printf 'Timed out waiting for %s at %s\n' "$label" "$url" >&2
      return 1
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  log "${label} is ready"
}

quay_network_name() {
  if [[ -n "$QUAY_NETWORK_NAME" ]]; then
    printf '%s\n' "$QUAY_NETWORK_NAME"
    return 0
  fi

  "$CONTAINER_RUNTIME" inspect quay-db \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    2>/dev/null | head -n 1
}

up_quay() {
  check_all
  if curl -fsS "${QUAY_URL}/health/instance" >/dev/null 2>&1; then
    log "Quay is already running at ${QUAY_URL}; reusing it"
    return 0
  fi

  log "Starting local Quay from ${QUAY_DIR}"
  (
    cd "$QUAY_DIR"
    if [[ -n "$QUAY_COMPOSE_PROJECT_NAME" ]]; then
      COMPOSE_PROJECT_NAME="$QUAY_COMPOSE_PROJECT_NAME" \
        DOCKER="$CONTAINER_RUNTIME" \
        BUILD_ANGULAR=false \
        make local-dev-up-react
    else
      DOCKER="$CONTAINER_RUNTIME" \
        BUILD_ANGULAR=false \
        make local-dev-up-react
    fi
  )
  wait_for_http "${QUAY_URL}/health/instance" "Quay" 240
  log "Quay UI: ${QUAY_URL}"
}

test_ingress() {
  check_all
  wait_for_http "${QUAY_URL}/health/instance" "Quay" 30
  log "Running real Quay spam ingress API smoke test"
  (
    cd "$QUAY_DIR/web"
    QUAY_URL="$QUAY_URL" node <<'NODE'
const { request } = require('@playwright/test');

const baseUrl = process.env.QUAY_URL || 'http://localhost:8080';

function uniqueName(prefix) {
  return `${prefix}${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

async function csrf(context) {
  const response = await context.get(`${baseUrl}/csrf_token`, {
    headers: {'X-Requested-With': 'XMLHttpRequest'},
  });
  if (!response.ok()) {
    throw new Error(`Failed to get CSRF token: ${response.status()} ${await response.text()}`);
  }
  return (await response.json()).csrf_token;
}

async function mutate(context, method, path, data) {
  const token = await csrf(context);
  return context[method](`${baseUrl}${path}`, {
    headers: {'X-CSRF-Token': token},
    data,
    timeout: 10_000,
  });
}

async function createAdminUser() {
  const context = await request.newContext({ignoreHTTPSErrors: true});
  try {
    const response = await mutate(context, 'post', '/api/v1/user/', {
      username: 'admin',
      password: 'password',
      email: 'admin@example.com',
    });
    if (response.ok()) {
      return;
    }
    const body = await response.text();
    if (!/already exists|already taken/i.test(body)) {
      throw new Error(`Failed to create admin user: ${response.status()} ${body}`);
    }
  } finally {
    await context.dispose();
  }
}

async function signIn() {
  const context = await request.newContext({ignoreHTTPSErrors: true});
  const response = await mutate(context, 'post', '/api/v1/signin', {
    username: 'admin',
    password: 'password',
  });
  if (!response.ok()) {
    const body = await response.text();
    await context.dispose();
    throw new Error(`Failed to sign in as admin/password: ${response.status()} ${body}`);
  }
  return context;
}

function assertStatus(response, expected, label) {
  if (response.status() !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${response.status()}`);
  }
}

(async () => {
  const configContext = await request.newContext({ignoreHTTPSErrors: true});
  let quayConfig;
  try {
    const configResponse = await configContext.get(`${baseUrl}/config`);
    if (!configResponse.ok()) {
      throw new Error(`Failed to read Quay config: ${configResponse.status()} ${await configResponse.text()}`);
    }
    quayConfig = await configResponse.json();
  } finally {
    await configContext.dispose();
  }

  if (quayConfig.features?.SPAM_DETECTION !== true) {
    throw new Error(
      'Quay is not exposing FEATURE_SPAM_DETECTION=true. Check that local-dev/stack/config.yaml is mounted into the running Quay container.',
    );
  }

  await createAdminUser();
  const context = await signIn();
  const orgName = uniqueName('spamingress');
  const spamRepo = uniqueName('spamrepo');
  const hamRepo = uniqueName('hamrepo');
  let hamCreated = false;

  try {
    const org = await mutate(context, 'post', '/api/v1/organization/', {
      name: orgName,
      email: `${orgName}@example.com`,
    });
    assertStatus(org, 201, 'create organization');

    const rejected = await mutate(context, 'post', '/api/v1/repository', {
      repo_kind: 'image',
      namespace: orgName,
      visibility: 'public',
      repository: spamRepo,
      description: 'free casino bonus crypto gift cards click now',
    });
    assertStatus(rejected, 400, 'create spam repository');

    const allowed = await mutate(context, 'post', '/api/v1/repository', {
      repo_kind: 'image',
      namespace: orgName,
      visibility: 'public',
      repository: hamRepo,
      description: 'trusted base image for python applications',
    });
    assertStatus(allowed, 201, 'create ham repository');
    hamCreated = true;

    const rejectedUpdate = await mutate(context, 'put', `/api/v1/repository/${orgName}/${hamRepo}`, {
      description: 'free casino bonus crypto gift cards click now',
    });
    assertStatus(rejectedUpdate, 400, 'update repository to spam description');

    console.log(`Verified enforced spam ingress against real Quay at ${baseUrl}`);
  } finally {
    if (hamCreated) {
      await mutate(context, 'delete', `/api/v1/repository/${orgName}/${hamRepo}`).catch(() => {});
    }
    await mutate(context, 'delete', `/api/v1/organization/${orgName}`).catch(() => {});
    await context.dispose();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
NODE
  )
}

up_service_tool() {
  check_all
  wait_for_http "${QUAY_URL}/health/instance" "Quay" 30
  if curl -fsS "$SERVICE_TOOL_URL" >/dev/null 2>&1 &&
    curl -fsS "${SERVICE_TOOL_API_URL}/healthcheck" >/dev/null 2>&1; then
    log "service-tool is already running at ${SERVICE_TOOL_URL}; reusing it"
    return 0
  fi

  local network_name
  network_name="$(quay_network_name)"
  if [[ -z "$network_name" ]]; then
    printf 'Unable to determine Quay compose network from quay-db. Is Quay running?\n' >&2
    exit 1
  fi

  log "Starting quay-service-tool from ${SERVICE_TOOL_DIR}"
  log "Using Quay network: ${network_name}"
  (
    cd "$SERVICE_TOOL_DIR"
    QUAY_NETWORK_NAME="$network_name" \
      "$CONTAINER_RUNTIME" compose down --remove-orphans || true
    SERVICE_TOOL_API_PORT="$SERVICE_TOOL_API_PORT" \
      SERVICE_TOOL_CLIENT_PORT="$SERVICE_TOOL_CLIENT_PORT" \
      QUAY_NETWORK_NAME="$network_name" \
      "$CONTAINER_RUNTIME" compose up -d --build
  )
  wait_for_http "${SERVICE_TOOL_API_URL}/healthcheck" "service-tool API" 180
  wait_for_http "$SERVICE_TOOL_URL" "service-tool frontend" 180
  log "service-tool UI: ${SERVICE_TOOL_URL}"
}

browse_service_tool() {
  check_all
  wait_for_http "$QUAY_URL" "Quay UI" 30
  wait_for_http "$SERVICE_TOOL_URL" "service-tool frontend" 30
  log "Opening Quay and service-tool UIs with system Chrome via Playwright"
  (
    cd "$SERVICE_TOOL_DIR/frontend"
    QUAY_URL="$QUAY_URL" \
    SERVICE_TOOL_URL="$SERVICE_TOOL_URL" \
      PLAYWRIGHT_SLOW_MO="$PLAYWRIGHT_SLOW_MO" \
      HOLD_SECONDS="$HOLD_SECONDS" \
      node <<'NODE'
const { chromium } = require('@playwright/test');

(async () => {
  const quayUrl = process.env.QUAY_URL || 'http://localhost:8080';
  const serviceToolUrl = process.env.SERVICE_TOOL_URL || 'http://localhost:9000';
  const slowMo = Number(process.env.PLAYWRIGHT_SLOW_MO || 0);
  const holdSeconds = Number(process.env.HOLD_SECONDS || 600);
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: false,
    slowMo,
  });
  const quayPage = await browser.newPage();
  await quayPage.goto(quayUrl, {
    waitUntil: 'domcontentloaded',
  });
  const serviceToolPage = await browser.newPage();
  await serviceToolPage.goto(serviceToolUrl, {
    waitUntil: 'domcontentloaded',
  });
  const spamDetectionLink = serviceToolPage.getByRole('link', { name: 'Spam Detection' });
  try {
    await spamDetectionLink.click({ timeout: 10_000 });
  } catch {
    await serviceToolPage.evaluate(() => {
      window.history.pushState({}, '', '/spam-detection');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
  }
  await serviceToolPage.waitForURL('**/spam-detection', { timeout: 10_000 });
  await serviceToolPage.getByText('Create classifier').waitFor({ timeout: 10_000 });
  await serviceToolPage.bringToFront();
  console.log(`Opened ${quayUrl}`);
  console.log(`Opened ${serviceToolUrl} and navigated to Spam Detection`);
  console.log(`Keeping browser open for ${holdSeconds} seconds. Press Ctrl-C to stop earlier.`);
  await new Promise((resolve) => setTimeout(resolve, holdSeconds * 1000));
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
NODE
  )
}

status_all() {
  if ! runtime_available; then
    log "Container runtime is not reachable: ${CONTAINER_RUNTIME}"
    if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
      log "Turn on Podman, then rerun this command."
    fi
    return 0
  fi

  log "Quay compose status"
  quay_compose ps || true

  log "service-tool compose status"
  (
    cd "$SERVICE_TOOL_DIR"
    "$CONTAINER_RUNTIME" compose ps
  ) || true
}

down_all() {
  if ! runtime_available; then
    log "Container runtime is not reachable: ${CONTAINER_RUNTIME}; nothing to stop from this shell"
    if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
      log "Turn on Podman before running up/test/service-tool."
    fi
    return 0
  fi

  log "Stopping service-tool"
  (
    cd "$SERVICE_TOOL_DIR"
    "$CONTAINER_RUNTIME" compose down --remove-orphans
  ) || true

  log "Stopping Quay"
  quay_compose down --remove-orphans || true
}

clean_all() {
  if ! runtime_available; then
    log "Container runtime is not reachable: ${CONTAINER_RUNTIME}; cannot remove compose volumes"
    if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
      log "Turn on Podman, then rerun this command."
    fi
    return 1
  fi

  log "Stopping service-tool and removing service-tool volumes"
  (
    cd "$SERVICE_TOOL_DIR"
    "$CONTAINER_RUNTIME" compose down --remove-orphans --volumes
  ) || true

  log "Stopping Quay and removing Quay volumes"
  quay_compose down --remove-orphans --volumes || true
}

case "${1:-}" in
  check)
    check_all
    ;;
  up)
    up_quay
    ;;
  test)
    test_ingress
    ;;
  service-tool)
    up_service_tool
    ;;
  browse)
    browse_service_tool
    ;;
  demo)
    up_quay
    test_ingress
    up_service_tool
    browse_service_tool
    ;;
  status)
    status_all
    ;;
  down)
    down_all
    ;;
  clean)
    clean_all
    ;;
  -h|--help|help|'')
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
