# Quay Service Tool


## Description

The purpose of this repository is to handle tasks like configuring or updating quay.
This is an internal tool and only Red Hat associates can access this. The tool is
implemented using React(Patternfly) on the frontend and Python(flask) on the backend.

## Prerequisites

The project expects the following environment variables in config.yaml:

- basic_auth:
  - username: Username to log into application. 
  - password: Password for the above user.
  - force: A boolean value. When set to True, forces app to use basic auth. 
- db:
  - host: The address where the database is hosted (Ed: 0.0.0.0)
  - name: The name of the database. 
  - port: The port that is used to connect with the database.
  - user: The name of the user that is used to make a build a secure database connection.
  - password: The password for the database user.
- is_local: A boolean value. When set to true, forces app to connect with postgres and if set to false, connects with msql. 

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

Run the below command to copy react front end files to `backend/static` to be served by the flask server.
```
  cp -r dist /home/parallels/Documents/quay-service-tool/backend/static
```

### Running flask server

Export the path of the `config.yaml` file in the `CONFIG_PATH` environment variable as:
```
  export CONFIG_PATH=/home/parallels/Documents/quay-service-tool/backend
```

Run the server using gunicorn in the `backend` directory as:
```
  gunicorn -k gevent -b 0.0.0.0:5000 app:app
```

You can now access the server at: `http://0.0.0.0:5000`. Enter the basic auth credentials set in `config.yaml` to login to the application.

To note: In `backend/app.py` the value of `static_folder` defined is absolute path. So, make sure to give the complete path. For example, `/home/parallels/Documents/quay-service-tool/backend`
