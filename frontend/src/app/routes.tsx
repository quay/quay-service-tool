import * as React from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { accessibleRouteChangeHandler } from '@app/utils/utils';
import UserService from "src/services/UserService";
import { SiteUtils } from '@app/SiteUtils/SiteUtils';
import { UserUtils } from '@app/UserUtils/UserUtils';
import { ExportCompliance } from '@app/ExportCompliance/ExportCompliance';
import { SpamDetection } from '@app/SpamDetection/SpamDetection';
import { NotFound } from '@app/NotFound/NotFound';
import { useDocumentTitle } from '@app/utils/useDocumentTitle';

let routeFocusTimer: number;
export interface IAppRoute {
  label?: string; // Excluding the label will exclude the route from the nav sidebar in AppLayout
  /* eslint-disable @typescript-eslint/no-explicit-any */
  component: React.ComponentType<any>;
  /* eslint-enable @typescript-eslint/no-explicit-any */
  exact?: boolean;
  path: string;
  title: string;
  isAsync?: boolean;
  routes?: undefined;
  permission?: string;
}

export interface IAppRouteGroup {
  label: string;
  routes: IAppRoute[];
}

export type AppRouteConfig = IAppRoute | IAppRouteGroup;

const AdminPerms = window.ADMIN_ROLE || process.env.ADMIN_ROLE;
const ExportPerms = window.EXPORT_COMPLIANCE_ROLE || process.env.EXPORT_COMPLIANCE_ROLE;
const SpamDetectionPerms = window.SPAM_DETECTION_ROLE || process.env.SPAM_DETECTION_ROLE;

const routes: AppRouteConfig[] = [
  {
    component: SiteUtils,
    exact: true,
    label: 'Site Utils',
    path: '/',
    title: 'Quay Service Tool | Site Utils',
    permission: AdminPerms,
  },
  {
    component: UserUtils,
    exact: true,
    isAsync: true,
    label: 'User Utils',
    path: '/user',
    title: 'Quay Service Tool | User Utils',
    permission: AdminPerms,
  },
  {
    component: ExportCompliance,
    exact: true,
    isAsync: true,
    label: 'Export Compliance',
    path: '/export-compliance',
    title: 'Quay Service Tool | Export Compliance',
    permission: ExportPerms
  },
  {
    component: SpamDetection,
    exact: true,
    isAsync: true,
    label: 'Spam Detection',
    path: '/spam-detection',
    title: 'Quay Service Tool | Spam Detection',
    permission: SpamDetectionPerms,
  },
];

// a custom hook for sending focus to the primary content container
// after a view has loaded so that subsequent press of tab key
// sends focus directly to relevant content
const useA11yRouteChange = (isAsync: boolean) => {
  const location = useLocation();
  const prevLocationRef = React.useRef(location);

  React.useEffect(() => {
    const prevLocation = prevLocationRef.current;
    if (!isAsync && prevLocation.pathname !== location.pathname) {
      routeFocusTimer = accessibleRouteChangeHandler();
    }
    prevLocationRef.current = location;
    return () => {
      window.clearTimeout(routeFocusTimer);
    };
  }, [isAsync, location]);
};

const RouteWithTitleUpdates = ({ component: Component, isAsync = false, title, ...rest }: IAppRoute) => {
  useA11yRouteChange(isAsync);
  useDocumentTitle(title);

  return <Route {...rest} element={<Component />} />;
};

const PageNotFound = ({ title }: { title: string }) => {
  useDocumentTitle(title);
  return <Route path="*" element={<NotFound />} />;
};

const flattenedRoutes: IAppRoute[] = routes.reduce(
  (flattened, route) => [...flattened, ...(route.routes ? route.routes : [route])],
  [] as IAppRoute[]
);


const AppRoutes = (): React.ReactElement => {

  return (
    <Routes>
      {flattenedRoutes.map(({ path, exact, component, title, isAsync }, idx) => (
        <RouteWithTitleUpdates
          path={path}
          component={component}
          key={idx}
          title={title}
          isAsync={isAsync}
        />
      ))}
      <PageNotFound title="404 Page Not Found" />
    </Routes>
  );
};

export { AppRoutes, routes };
