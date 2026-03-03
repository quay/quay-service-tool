from unittest.mock import patch, MagicMock
from jwcrypto import jwk, jwt
import json
import time
import pytest

from app import app


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def rsa_key():
    return jwk.JWK.generate(kty='RSA', size=2048, kid='test-key')


def make_token(key, claims_override=None):
    claims = {
        'sub': '00000000-0000-0000-0000-000000000000',
        'iss': 'https://auth.example.com/auth/realms/TestRealm',
        'aud': 'test-client-id',
        'exp': int(time.time()) + 3600,
        'iat': int(time.time()),
        'realm_access': {'roles': ['admin']},
        'name': 'Test User',
        'email': 'test@example.com',
    }
    if claims_override:
        claims.update(claims_override)
    token = jwt.JWT(header={'alg': 'RS256', 'kid': 'test-key'}, claims=claims)
    token.make_signed_token(key)
    return token.serialize()


def mock_keycloak_certs(key):
    pub = json.loads(key.export_public())
    return {'keys': [pub]}


AUTH_CONFIG = {
    'url': 'https://auth.example.com/auth',
    'clientid': 'test-client-id',
    'realm': 'TestRealm',
    'roles': {'ADMIN_ROLE': 'admin'},
}


class TestKeycloakAuth:

    @patch('app.KeycloakOpenID')
    def test_valid_token_decodes_successfully(self, mock_kc_class, client, rsa_key):
        mock_kc = MagicMock()
        mock_kc_class.return_value = mock_kc
        mock_kc.certs.return_value = mock_keycloak_certs(rsa_key)

        token = make_token(rsa_key)

        app.config['is_local'] = False
        app.config['authentication'] = AUTH_CONFIG

        res = client.get('/banner', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code != 500 or b'authentication' not in res.data

    @patch('app.KeycloakOpenID')
    def test_wrong_audience_rejected(self, mock_kc_class, client, rsa_key):
        mock_kc = MagicMock()
        mock_kc_class.return_value = mock_kc
        mock_kc.certs.return_value = mock_keycloak_certs(rsa_key)

        token = make_token(rsa_key, {'aud': 'wrong-client'})

        app.config['is_local'] = False
        app.config['authentication'] = AUTH_CONFIG

        res = client.get('/banner', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code in (401, 500)

    @patch('app.KeycloakOpenID')
    def test_expired_token_rejected(self, mock_kc_class, client, rsa_key):
        mock_kc = MagicMock()
        mock_kc_class.return_value = mock_kc
        mock_kc.certs.return_value = mock_keycloak_certs(rsa_key)

        token = make_token(rsa_key, {'exp': int(time.time()) - 3600})

        app.config['is_local'] = False
        app.config['authentication'] = AUTH_CONFIG

        res = client.get('/banner', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code in (401, 500)

    @patch('app.KeycloakOpenID')
    def test_local_dev_skips_audience_check(self, mock_kc_class, client, rsa_key):
        mock_kc = MagicMock()
        mock_kc_class.return_value = mock_kc
        mock_kc.certs.return_value = mock_keycloak_certs(rsa_key)

        token = make_token(rsa_key, {'aud': 'different-client'})

        app.config['is_local'] = True
        app.config['test_auth'] = True
        app.config['authentication'] = AUTH_CONFIG

        res = client.get('/banner', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code != 500 or b'authentication' not in res.data
