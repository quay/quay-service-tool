from unittest.mock import Mock, patch
from app import app
from utils import check_protected_namespace
import pytest
import json


PROTECTED_AUTH_CONFIG = {
    'url': 'https://auth.example.com/auth',
    'clientid': 'test-client-id',
    'realm': 'TestRealm',
    'roles': {
        'ADMIN_ROLE': 'admin-role',
        'EXPORT_COMPLIANCE_ROLE': 'export-compliance-role',
        'PROTECTED_ADMIN_ROLE': 'protected-admin-role',
    },
    'protected_namespaces': [
        'openshift-release-dev',
        'redhat-prod',
        'redhat',
        'redhat-user-workloads',
        'openshift',
        'redhat-pending',
        'redhat-services-prod',
        'redhat-services-pending',
        'openshift-logging',
        'openshift-pipeline',
        'openshiftio',
    ],
}


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture(autouse=True)
def enable_auth():
    original_local = app.config.get('is_local')
    original_test_auth = app.config.get('test_auth')
    original_auth = app.config.get('authentication')
    app.config['is_local'] = True
    app.config['test_auth'] = True
    app.config['authentication'] = PROTECTED_AUTH_CONFIG
    yield
    app.config['is_local'] = original_local
    app.config['test_auth'] = original_test_auth
    app.config['authentication'] = original_auth


def mock_user_with_roles(roles):
    return Mock(
        is_authenticated=True,
        email='test@example.com',
        username='Test User',
        realm_access={'roles': roles},
    )


class TestCheckProtectedNamespace:

    @patch('utils.current_user')
    def test_blocks_protected_namespace_without_role(self, mock_current_user):
        mock_current_user.realm_access = {'roles': ['admin-role']}
        with app.test_request_context():
            result = check_protected_namespace('redhat-prod')
        assert result is not None
        assert result.status_code == 403
        assert b'protected' in result.data.lower()

    @patch('utils.current_user')
    def test_allows_protected_namespace_with_role(self, mock_current_user):
        mock_current_user.realm_access = {'roles': ['admin-role', 'protected-admin-role']}
        with app.test_request_context():
            result = check_protected_namespace('redhat-prod')
        assert result is None

    @patch('utils.current_user')
    def test_allows_non_protected_namespace(self, mock_current_user):
        mock_current_user.realm_access = {'roles': ['admin-role']}
        with app.test_request_context():
            result = check_protected_namespace('some-random-user')
        assert result is None

    @patch('utils.current_user')
    def test_case_insensitive_match(self, mock_current_user):
        mock_current_user.realm_access = {'roles': ['admin-role']}
        with app.test_request_context():
            result = check_protected_namespace('RedHat-Prod')
        assert result is not None
        assert result.status_code == 403

    @patch('utils.current_user')
    def test_none_namespace_allowed(self, mock_current_user):
        with app.test_request_context():
            result = check_protected_namespace(None)
        assert result is None

    @patch('utils.current_user')
    def test_blocks_all_protected_namespaces(self, mock_current_user):
        mock_current_user.realm_access = {'roles': ['admin-role']}
        for ns in PROTECTED_AUTH_CONFIG['protected_namespaces']:
            with app.test_request_context():
                result = check_protected_namespace(ns)
            assert result is not None, f"Expected {ns} to be blocked"
            assert result.status_code == 403

    @patch('utils.current_user')
    def test_blocks_when_no_realm_access(self, mock_current_user):
        mock_current_user.realm_access = None
        with app.test_request_context():
            result = check_protected_namespace('redhat')
        assert result is not None
        assert result.status_code == 403

    def test_local_dev_bypass(self):
        app.config['test_auth'] = False
        with app.test_request_context():
            result = check_protected_namespace('redhat-prod')
        assert result is None


class TestProtectedNamespaceEndpoints:

    @patch('tasks.user.user')
    def test_delete_protected_user_blocked(self, mock_user, client):
        app.config['is_local'] = False
        mock_user.get_namespace_user.return_value = Mock(
            is_authenticated=True, realm_access={'roles': ['admin-role']},
            email='test@example.com', username='Test User',
        )
        res = client.delete('/user/redhat-prod')
        assert res.status_code in (401, 403)

    @patch('tasks.user.user')
    def test_enable_protected_user_blocked(self, mock_user, client):
        app.config['is_local'] = False
        mock_user.get_namespace_user.return_value = Mock(
            is_authenticated=True, realm_access={'roles': ['admin-role']},
            email='test@example.com', username='Test User',
        )
        res = client.put('/user/redhat-prod?enable=true')
        assert res.status_code in (401, 403)

    @patch('tasks.user.user')
    def test_delete_non_protected_user_not_blocked_by_guard(self, mock_user, client):
        app.config['test_auth'] = False
        mock_user.get_namespace_user.return_value = Mock(id=1, username='some-user', enabled=True)
        mock_user.mark_namespace_for_deletion.return_value = None
        res = client.delete('/user/some-user')
        assert res.status_code != 403
