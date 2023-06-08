import Keycloak from "keycloak-js";

const AUTH_REALM = window.AUTH_REALM || process.env.AUTH_REALM;
const AUTH_URL = window.AUTH_URL || process.env.AUTH_URL;
const AUTH_CLIENTID = window.AUTH_CLIENTID || process.env.AUTH_CLIENTID;

const KeycloakInstance = new Keycloak( {
                                        "realm": AUTH_REALM,
                                        "url": AUTH_URL,
                                        "clientId": AUTH_CLIENTID,
                                      });

const initKeycloak = (onAuthenticatedCallback) => {
  KeycloakInstance.init({
    onLoad: 'check-sso',
    pkceMethod: 'S256',
  })
    .then((authenticated) => {
      if (authenticated) {
        onAuthenticatedCallback();
      } else {
        login();
      }
    })
};

const login = KeycloakInstance.login;

const logout = KeycloakInstance.logout;

const getToken = () => KeycloakInstance.token;

const isLoggedIn = () => !!KeycloakInstance.token;

const email = KeycloakInstance.email;

const updateToken = (successCallback) =>
  KeycloakInstance.updateToken(5)
    .then(successCallback)
    .catch(login);

const username = () => KeycloakInstance.tokenParsed?.preferred_username;

const hasRealmRole = (role) => process.env.NODE_ENV == "production" ? KeycloakInstance.hasRealmRole(role) : true;

const UserService = {
  Keycloak,
  initKeycloak,
  login,
  logout,
  isLoggedIn,
  getToken,
  email,
  updateToken,
  username,
  hasRealmRole
};

export default UserService;
