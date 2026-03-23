FROM node:22@sha256:f90672bf4c76dfc077d17be4c115b1ae7731d2e8558b457d86bca42aeb193866

WORKDIR /usr/src/app

COPY package*.json ./

RUN npm install --legacy-peer-deps

COPY . .

EXPOSE 9000

CMD [ "npm", "run", "start:dev" ]
