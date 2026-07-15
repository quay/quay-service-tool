# Quay Service Tool


## Description

The purpose of this repository is to handle tasks like configuring or updating quay.
This is an internal tool and only Red Hat associates can access this. The tool is
implemented using React(Patternfly) on the frontend and Python(flask) on the backend.

## Prerequisites

The project expects the following environment variables in config.yaml:

- authentication:
  - url: Keycloak authentication url
  - clientid: Keycloak client id
  - realm: Keycloak realm, the client id belongs to
- DB_URI: databaseEngine://databaseUser:databasePassword@databaseHost:databasePort/databaseName
- is_local: A boolean value. When set to true, forces app to connect with postgres and if set to false, connects with mysql.
- ENV: Development/Production environment.

Run the Quay app and its dependencies. Make sure that the quay-db is running.
Pass the database credentials for authenticating into the quay db to the `config.yaml`.

You can find the reference for config.yaml at `backend\config.yaml`

Remove the `node_modules` folder under frontend (if exists)

## Testing

### Backend Tests
Add the following environment variables:
`TESTING=true` - This will prepare certain configurations such as auth and database connections for testing.
`CONFIG_PATH=<path to repo>/backend/config` - Configuration to be used for testing.

To run the tests:
`cd backend && export CONFIG_PATH="config" TESTING=true && pytest -v`

### Frontend Tests

Frontend tests are configured with the following pnpm script:
`cd frontend && pnpm test`

### Spam detection end-to-end demo

The spam detection demo starts the Quay ingress implementation and service
tool together, then opens both UIs in separate system Chrome tabs. The visible
workflow:

1. Signs in to Quay and attempts to create a repository with a spam
   description, showing the ingress rejection in the Quay UI.
2. Creates a synthetic empty legacy repository that represents spam content
   predating ingress enforcement.
3. Seeds a temporary service-tool classifier from synthetic examples, previews
   the legacy repository, and runs a review scan.
4. Quarantines the flagged repository and verifies the owner-facing notice in
   Quay.
5. Restores the repository and verifies the original description returns in
   Quay.
6. Reopens the mistaken restore with a required reason and quarantines the
   repository again without changing the classifier.
7. Verifies the final Quay quarantine notice and the complete service-tool
   audit history.

Meaningful clicks and input focus are marked with an animated yellow ring. The
browser remains open for ten minutes after the workflow completes.

Prerequisites:

- Check out quay/quay#6154 and this service-tool PR.
- Install Node.js, Corepack, `make`, `curl`, and system Chrome.
- Start Podman or Docker with Compose support. The demo does not start or
  modify a Podman machine.
- Keep ports `8080`, `5001`, and `9000` available.
- Install the browser dependencies once:

```sh
corepack pnpm --dir /absolute/path/to/quay/web install --frozen-lockfile
corepack pnpm@10.28.2 --dir /absolute/path/to/quay-service-tool/frontend install --frozen-lockfile
```

The Quay PR checkout contains the required local classifier artifact and spam
detection configuration. Validate all prerequisites without starting anything:

```sh
QUAY_DIR=/absolute/path/to/quay \
make -C /absolute/path/to/quay-service-tool spam-demo-check
```

From the service-tool repository, run:

```sh
make spam-demo
```

From any directory, or when the Quay checkout is not the default sibling named
`quay`, run:

```sh
QUAY_DIR=/absolute/path/to/quay \
make -C /absolute/path/to/quay-service-tool spam-demo
```

Use `PLAYWRIGHT_SLOW_MO` to change individual browser action timing,
`DEMO_STEP_DELAY` to change the pause between visible stages, and
`DEMO_CLICK_DELAY` to change how long click highlighting remains visible.
`HOLD_SECONDS` controls how long the browser remains open. For a differently
located Quay checkout or a slower presentation:

```sh
QUAY_DIR=/path/to/quay PLAYWRIGHT_SLOW_MO=1500 DEMO_STEP_DELAY=10000 DEMO_CLICK_DELAY=2000 HOLD_SECONDS=900 make spam-demo
```

Stop the demo while preserving volumes, or remove its volumes completely:

```sh
QUAY_DIR=/absolute/path/to/quay \
make -C /absolute/path/to/quay-service-tool spam-demo-down

QUAY_DIR=/absolute/path/to/quay \
make -C /absolute/path/to/quay-service-tool spam-demo-clean
```

`make spam-demo-check` validates paths, configuration, required commands, and
container-runtime availability without starting either application.

## Quick Start

### Starting application

Start the application using docker-compose.yml.

`docker-compose up -d`

## Starting servers individually

### Backend

The application uses: Python 3.13. So, please create a Python Environment - 3.13 and install the requirements using [uv](https://github.com/astral-sh/uv).

```
  uv sync
```

Export the path of the `config.yaml` file in the `CONFIG_PATH` environment variable as:
```
  export CONFIG_PATH=/home/parallels/Documents/quay-service-tool/backend/config
```

Run the server using gunicorn in the `backend` directory as:
```
  uv run gunicorn -k gevent -b 0.0.0.0:5000 app:app
```
This allows flask to serve requests on `http://0.0.0.0:5000`.

### Frontend

Run `pnpm install` to install the node modules.

After successful execution of the command, run `pnpm build` to build the application bundles.

You can run the below command to start the front-end server.
```
  pnpm start:dev
```
You can now access the application at: `http://0.0.0.0:9000`.

### Keycloak - Auth server

You can get a keycloak server running using the command below. This starts the keycloak server on the port 8081.
You can skip this if you are running locally and don't require user authentication to the application.


`docker run --name keycloak -p 8081:8080 -e KEYCLOAK_USER=admin -e KEYCLOAK_PASSWORD=password jboss/keycloak`

You can refer to this document to set up a Keycloak realm, client and user - https://scalac.io/blog/user-authentication-keycloak-1/

The details of the keycloak configuration needs to be updated in backend/config/config.yaml and frontend/.env.
