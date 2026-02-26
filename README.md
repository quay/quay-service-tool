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

Frontend tests are configured with the following npm script:
`cd frontend && npm run test`

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

Run `npm install` to install the node modules.

After successful execution of the command, run `npm run build` to build the application bundles.

You can run the below command to start the front-end server.
```
  npm run start:dev
```
You can now access the application at: `http://0.0.0.0:9000`.

### Keycloak - Auth server

You can get a keycloak server running using the command below. This starts the keycloak server on the port 8081.
You can skip this if you are running locally and don't require user authentication to the application.


`docker run --name keycloak -p 8081:8080 -e KEYCLOAK_USER=admin -e KEYCLOAK_PASSWORD=password jboss/keycloak`

You can refer to this document to set up a Keycloak realm, client and user - https://scalac.io/blog/user-authentication-keycloak-1/

The details of the keycloak configuration needs to be updated in backend/config/config.yaml and frontend/.env.
