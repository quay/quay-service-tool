import Keycloak from "keycloak-js";

const KeycloakInstance = new Keycloak( {
                                        "realm": process.env.AUTH_REALM,
                                        "url": process.env.AUTH_URL,
                                        "clientId": process.env.AUTH_CLIENTID,
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

const hasRole = (roles) => roles.some((role) => KeycloakInstance.hasRealmRole(role));

const UserService = {
  initKeycloak,
  login,
  logout,
  isLoggedIn,
  getToken,
  email,
  updateToken,
  username,
  hasRole,
};

export default UserService;
