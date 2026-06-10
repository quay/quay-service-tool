from unittest.mock import Mock, patch, call, PropertyMock
from app import app
import json
import pytest as pytest

@pytest.fixture
def client():
    return app.test_client()

def get_mock_context():
    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=(Mock(), None))
    mock_context.__exit__ = Mock(return_value=None)
    return mock_context

def make_mock_user(**overrides):
    defaults = dict(
        id=1, username='test', email='test@example.com', enabled=True,
        stripe_id='cus_123', last_accessed='2024-01-01', organization=False,
        company='TestCo', creation_date='2023-01-01',
        invoice_email_address='billing@example.com',
    )
    defaults.update(overrides)
    return Mock(**defaults)

class TestUserGet:

    @patch('tasks.user.user')
    def test_return_user(self, mock_user, client):
        mock_user.get_namespace_user.return_value = Mock(id=1, username='test', enabled=False)
        res = client.get('/user/test')
        assert res.status_code == 200
        assert res.data == b'{"username": "test", "enabled": false}'

    @patch('tasks.user.user')
    def test_user_not_found(self, mock_user, client):
        mock_user.get_namespace_user.return_value = None
        res = client.get('/user/test')
        assert res.status_code == 404
        assert res.data == b'{"message": "Could not find user test"}'

    @patch('tasks.user.user')
    def test_error_during_get(self, mock_user, client):
        mock_user.get_namespace_user.return_value = Mock(side_effect=RuntimeError())
        res = client.get('/user/test')
        assert res.status_code == 500
        assert res.data == b'{"message": "Unable to fetch user test"}'


class TestUserPut:
    @patch('tasks.user.db_transaction')
    @patch('tasks.user.user')
    def test_enable_user(self, mock_user, mock_db_transaction, client):
        mock_db_transaction.return_value = get_mock_context()
        mock_returned_user = Mock(id=1, username='test', enabled=False)
        mock_user.get_namespace_user.return_value = mock_returned_user
        res = client.put('/user/test?enable=true')

        mock_returned_user.save.assert_called_once()
        assert mock_returned_user.enabled is True
        assert res.status_code == 200
        assert res.data == b'{"message": "User updated successfully", "user": "test", "enabled": true}'

    @patch('tasks.user.db_transaction')
    @patch('tasks.user.user')
    def test_disable_user(self, mock_user, mock_db_transaction, client):
        mock_db_transaction.return_value = get_mock_context()
        mock_returned_user = Mock(id=1, username='test', enabled=True)
        mock_user.get_namespace_user.return_value = mock_returned_user
        res = client.put('/user/test?enable=false')

        mock_returned_user.save.assert_called_once()
        assert mock_returned_user.enabled is False
        assert res.data == b'{"message": "User updated successfully", "user": "test", "enabled": false}'
        assert res.status_code == 200

    @patch('tasks.user.user')
    def test_error(self, mock_user, client):
        mock_user.get_namespace_user = Mock(side_effect=RuntimeError())
        res = client.put('/user/test?enable=false')
        assert res.status_code == 500
        assert res.data == b'{"message": "Unable to update enable status"}'

    def test_missing_parameters(self, client):
        res = client.put('/user/test')
        assert res.status_code == 400
        assert res.data == b'{"message": "Parameter \'enable\' required"}'

    @patch('tasks.user.user')
    def test_user_not_found(self, mock_user, client):
        mock_user.get_namespace_user.return_value = None
        res = client.put('/user/test?enable=true')
        assert res.status_code == 404
        assert res.data == b'{"message": "Could not find user test"}'

    @patch('tasks.user.user')
    def test_user_already_enabled(self, mock_user, client):
        mock_returned_user = Mock(id=1, username='test', enabled=True)
        mock_user.get_namespace_user.return_value = mock_returned_user
        res = client.put('/user/test?enable=true')
        assert res.status_code == 400
        assert res.data == b'{"message": "User test already enabled"}'

    @patch('tasks.user.user')
    def test_user_already_disabled(self, mock_user, client):
        mock_returned_user = Mock(id=1, username='test', enabled=False)
        mock_user.get_namespace_user.return_value = mock_returned_user
        res = client.put('/user/test?enable=false')
        assert res.status_code == 400
        assert res.data == b'{"message": "User test already disabled"}'


class TestFetchUserFromName:

    @patch('tasks.user.user')
    def test_returns_user_with_account_numbers(self, mock_user, client):
        mock_found_user = make_mock_user()
        mock_user.get_namespace_user.return_value = mock_found_user
        mock_user.get_private_repo_count.return_value = 5
        mock_user.get_public_repo_count.return_value = 10

        mock_marketplace = Mock()
        mock_marketplace.get_account_number.return_value = [12345, 67890]
        app.extensions['marketplace_user_api'] = mock_marketplace

        res = client.get('/quayusername/test')
        data = json.loads(res.data)

        assert res.status_code == 200
        assert data['account_numbers'] == [12345, 67890]
        mock_marketplace.get_account_number.assert_called_once_with(mock_found_user)

    @patch('tasks.user.user')
    def test_user_not_found(self, mock_user, client):
        mock_user.get_namespace_user.return_value = None
        res = client.get('/quayusername/nonexistent')
        assert res.status_code == 404

    @patch('tasks.user.user')
    def test_account_numbers_none(self, mock_user, client):
        mock_user.get_namespace_user.return_value = make_mock_user()
        mock_user.get_private_repo_count.return_value = 0
        mock_user.get_public_repo_count.return_value = 0

        mock_marketplace = Mock()
        mock_marketplace.get_account_number.return_value = None
        app.extensions['marketplace_user_api'] = mock_marketplace

        res = client.get('/quayusername/test')
        data = json.loads(res.data)

        assert res.status_code == 200
        assert data['account_numbers'] is None


class TestFetchUserFromEmail:

    @patch('tasks.user.user')
    def test_returns_user_with_account_numbers(self, mock_user, client):
        mock_found_user = make_mock_user()
        mock_user.find_user_by_email.return_value = mock_found_user
        mock_user.get_private_repo_count.return_value = 5
        mock_user.get_public_repo_count.return_value = 10

        mock_marketplace = Mock()
        mock_marketplace.get_account_number.return_value = [67890]
        app.extensions['marketplace_user_api'] = mock_marketplace

        res = client.get('/quayuseremail/test@example.com')
        data = json.loads(res.data)

        assert res.status_code == 200
        assert data['account_numbers'] == [67890]
        mock_marketplace.get_account_number.assert_called_once_with(mock_found_user)

    @patch('tasks.user.user')
    def test_user_not_found(self, mock_user, client):
        mock_user.find_user_by_email.return_value = None
        res = client.get('/quayuseremail/missing@example.com')
        assert res.status_code == 404

    @patch('tasks.user.user')
    def test_account_numbers_none(self, mock_user, client):
        mock_user.find_user_by_email.return_value = make_mock_user()
        mock_user.get_private_repo_count.return_value = 0
        mock_user.get_public_repo_count.return_value = 0

        mock_marketplace = Mock()
        mock_marketplace.get_account_number.return_value = None
        app.extensions['marketplace_user_api'] = mock_marketplace

        res = client.get('/quayuseremail/test@example.com')
        data = json.loads(res.data)

        assert res.status_code == 200
        assert data['account_numbers'] is None
