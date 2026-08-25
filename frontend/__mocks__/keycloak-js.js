// Jest mock for keycloak-js (ESM-only in v26, needs CJS mock for Jest 26)
class Keycloak {
  constructor(config) {
    this.config = config;
    this.authenticated = false;
    this.token = undefined;
    this.tokenParsed = undefined;
    this.refreshToken = undefined;
    this.refreshTokenParsed = undefined;
    this.idToken = undefined;
    this.idTokenParsed = undefined;
    this.realmAccess = undefined;
    this.resourceAccess = undefined;
    this.subject = undefined;
    this.timeSkew = 0;
    this.didInitialize = false;
  }

  init() {
    return Promise.resolve(false);
  }

  login() {
    return Promise.resolve();
  }

  logout() {
    return Promise.resolve();
  }

  register() {
    return Promise.resolve();
  }

  accountManagement() {
    return Promise.resolve();
  }

  updateToken() {
    return Promise.resolve(false);
  }

  clearToken() {}

  hasRealmRole() {
    return false;
  }

  hasResourceRole() {
    return false;
  }

  isTokenExpired() {
    return true;
  }

  loadUserProfile() {
    return Promise.resolve({});
  }

  loadUserInfo() {
    return Promise.resolve({});
  }
}

module.exports = Keycloak;
module.exports.default = Keycloak;
module.exports.__esModule = true;
