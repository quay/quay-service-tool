import Keycloak from 'keycloak-js'

const keycloakConfig = {
  realm: "Demo",
  url: "http://localhost:8081/auth/",
  clientId: "quay-service-tool",
  }

const keycloak = Keycloak(keycloakConfig);
export default keycloak
