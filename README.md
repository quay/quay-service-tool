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
- db:
  - host: The address where the database is hosted (Eg: 0.0.0.0)
  - name: The name of the database. 
  - port: The port that is used to connect with the database.
  - user: The name of the user that is used to make a build a secure database connection.
  - password: The password for the database user.
- is_local: A boolean value. When set to true, forces app to connect with postgres and if set to false, connects with mysql.

Run the Quay app and its dependencies. Make sure that the quay-db is running.
Pass the database credentials for authenticating into the quay db to the `config.yaml`.

You can find the reference for config.yaml at `backend\config.yaml`

Remove the `node_modules` folder under frontend (if exists)

## Quick Start

### Keycloak - Auth server

You can get a keycloak server running using the command below. This starts the keycloak server on the port 8081.

`docker run --name keycloak -p 8081:8080 -e KEYCLOAK_USER=admin -e KEYCLOAK_PASSWORD=password jboss/keycloak`

You can refer to this document to set up a Keycloak realm, client and user - https://scalac.io/blog/user-authentication-keycloak-1/

The details of the keycloak configuration needs to be updated in backend/config/config.yaml and frontend/.env.

### Update package.json

Change the `webpack.prod.js` at `frontend/package.json` to `webpack.dev.js` in the build command. 

### Starting application

Start the application using docker-compose.yml.

`docker-compose up -d`

## Starting servers individually

### Backend

Export the path of the `config.yaml` file in the `CONFIG_PATH` environment variable as:
```
  export CONFIG_PATH=/home/parallels/Documents/quay-service-tool/backend
```

Run the server using gunicorn in the `backend` directory as:
```
  gunicorn -k gevent -b 0.0.0.0:5000 app:app
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
