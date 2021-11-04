# Quay Service Tool


## Description

The purpose of this repository is to handle tasks like configuring or updating quay.
This is an internal tool and only Red Hat associates can access this. The tool is
implemented using React(Patternfly) on the frontend and Python(flask) on the backend.

## Prerequisites

The project expects the following environment variables in config.yaml:

(To note: The below basic_auth key will not be needed once the tool uses SSO for login.)
- basic_auth:
  - username: Username to log into application. 
  - password: Password for the above user.
  - force: A boolean value. When set to True, forces app to use basic auth. 
- db:
  - host: The address where the database is hosted (Eg: 0.0.0.0)
  - name: The name of the database. 
  - port: The port that is used to connect with the database.
  - user: The name of the user that is used to make a build a secure database connection.
  - password: The password for the database user.
- is_local: A boolean value. When set to true, forces app to connect with postgres and if set to false, connects with mysql.

Please set the environment variable `IS_LOCAL` to True (if running the tool locally), if not to False, like:
```
 export IS_LOCAL=True
```

This variable is used to determine the database server connection.
On local, the tool connects to the postgres server and on prod, to the mysql server. 

Run the Quay app and its dependencies. Make sure that the quay-db is running.
Pass the credentials for authenticating into the quay db to the `config.yaml`.

Please find the reference for config.yaml at `backend\config.yaml`

Remove the `node_modules` folder under frontend (if exists)

## Running

### Setting up frontend server

Run `npm install` to install the node modules.

After successful execution of the command, run `npm run build` to build the application bundles.

### Running flask server

Export the path of the `config.yaml` file in the `CONFIG_PATH` environment variable as:
```
  export CONFIG_PATH=/home/parallels/Documents/quay-service-tool/backend
```

Run the server using gunicorn in the `backend` directory as:
```
  gunicorn -k gevent -b 0.0.0.0:5000 app:app
```
This allows flask to serve requests on `http://0.0.0.0:5000`.

### Development Environment

To note: Please use the below step in a development environment. This is not required in a production environment

In the file `frontend/webpack.dev.js`, please change the url in the proxy dictionary to point to `http://0.0.0.0:5000`.
You can run the below command to start the front-end server.
```
  npm run start:dev
```
You can now access the application at: `http://0.0.0.0:9000`. Enter the basic auth credentials set in `config.yaml` to login to the application.

### Production Environment

To note: This step is not needed in a development environment

Run the below command to copy react front end files to `backend/static` to be served by the flask server.
```
  cp -r dist /home/parallels/Documents/quay-service-tool/backend/static
```

You can now access the application at: `http://0.0.0.0:5000`. Enter the basic auth credentials set in `config.yaml` to login to the application.
