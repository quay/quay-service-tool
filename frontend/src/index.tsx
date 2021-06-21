import React from "react";
import ReactDOM from "react-dom";
import App from '@app/index';
import axios from "axios";

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

let banners = {};
axios.get('banner').then(function (response) {
  banners = response.data;
  ReactDOM.render(<App banners={response.data}/>, document.getElementById("root") as HTMLElement);
}).catch(function (error) {
  console.log(error);
});
