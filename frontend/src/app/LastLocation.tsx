import * as React from 'react';
import { Location, useLocation } from 'react-router-dom';

const LastLocationContext = React.createContext<Location | null>(null);

const LastLocationProvider: React.FunctionComponent<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const previousLocation = React.useRef<Location | null>(null);
  const lastLocation = previousLocation.current;

  React.useEffect(() => {
    previousLocation.current = location;
  }, [location]);

  return <LastLocationContext.Provider value={lastLocation}>{children}</LastLocationContext.Provider>;
};

const useLastLocation = (): Location | null => React.useContext(LastLocationContext);

export { LastLocationProvider, useLastLocation };
