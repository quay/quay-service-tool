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

  const [banners, setBanners] = React.useState({'banners': []});
  React.useEffect(() => {
    const banners = [];
    HttpService.axiosClient.get('banner')
      .then(function (response) {
        banners = response.data;
        setBanners(banners);
      })
      .catch(function (error) {
        if (error.response.status == 401) {
          UserService.logout();
        }
        else {
          console.log(error);
        }
      });
  }, []);

  return (
    <Router>
      <AppLayout >
        <AppRoutes {...banners}/>
      </AppLayout>
    </Router>
  );
}

export default hot(App);
