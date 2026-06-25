# AGENTS.md - Quay Service Tool

Internal admin tool for running Quay admin tasks (user lookup, banners, robot tokens, org owner management, username changes, federated users, email updates, marketplace integration).

## Architecture

- **Frontend** (`frontend/`): React 17 + PatternFly 4 + TypeScript, built with webpack, managed with pnpm
- **Backend** (`backend/`): Python 3.12 + Flask/Flask-RESTful, managed with uv
- **Auth**: Keycloak-based authentication with role-based access (`backend/utils.py`)
- **Database**: Connects to Quay's PostgreSQL via Quay's own ORM (Peewee, imported from the `quay` package pinned to a commit SHA in `pyproject.toml`)
- **Config**: `backend/config/config.yaml` — DB_URI, Keycloak settings, marketplace API settings
- **API resources**: `backend/tasks/` — banner, federateduser, org_owner, robot_token, user, username
- **Frontend pages**: `frontend/src/app/` — UserUtils, SiteUtils, ExportCompliance, Support

## Local Development

Requires a running Quay app + database (joins the `quay_default` Docker network).

```bash
make local-dev-up     # start full stack (podman compose / docker compose)
make local-dev-down   # shut down
```

## Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm ci-checks        # type-check + lint + test (runs in CI)
pnpm start:dev         # webpack dev server on :3000
pnpm test              # jest unit tests
pnpm test:e2e          # playwright e2e tests
pnpm lint              # eslint
pnpm type-check        # tsc --noEmit
```

## Backend

```bash
cd backend
uv sync --group dev
uv run pytest          # unit tests (requires CONFIG_PATH=config)
```

System dependency: `libldap-dev libsasl2-dev` (needed for python-ldap via quay dependency).

## CI

GitHub Actions on every PR and push to main:
- `backend-unit.yml` — `uv run pytest` with `CONFIG_PATH=config`
- `frontend-unit.yml` — `pnpm ci-checks` (type-check + lint + test)
- `frontend-e2e.yml` — Playwright e2e tests

Tekton pipelines in `.tekton/` handle build/deploy for OpenShift.

## Commit Convention

```
type(scope): description
```

Types: `fix`, `feat`, `test`, `refactor`, `docs`, `chore`, `config`

PR titles: `PROJQUAY-XXXXX: type(scope): description` or `NO-ISSUE: ...`
