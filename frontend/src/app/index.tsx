import { hot } from 'react-hot-loader/root';
import * as React from 'react';
import '@patternfly/react-core/dist/styles/base.css';
import { BrowserRouter as Router } from 'react-router-dom';
import { AppLayout } from '@app/AppLayout/AppLayout';
import { AppRoutes } from '@app/routes';
import '@app/app.css';
import HttpService from "../services/HttpService";
import UserService from "../services/UserService";

const App: React.FunctionComponent = (props) => {

  return (
    <Router>
      <AppLayout >
        <AppRoutes/>
      </AppLayout>
    </Router>
  );
}

export default hot(App);
