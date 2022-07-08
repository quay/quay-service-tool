import React from "react";
import ReactDOM from "react-dom";
import App from '@app/index';
import HttpService from "./services/HttpService";
import UserService from "./services/UserService";

if (process.env.NODE_ENV !== "production") {
  const config = {
    rules: [
      {
        id: 'color-contrast',
        enabled: false
      }
    ]
  };
  // eslint-disable-next-line @typescript-eslint/no-var-requires, no-undef
  const axe = require("react-axe");
  axe(React, ReactDOM, 1000, config);
}


const renderApp = () => ReactDOM.render(<App />, document.getElementById("root") as HTMLElement);
if (process.env.NODE_ENV !== "production") {
  renderApp();
}
else {
  UserService.initKeycloak(renderApp);
}
HttpService.configure();
