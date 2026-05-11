from unittest.mock import Mock, patch, call, PropertyMock
from app import app
import pytest as pytest

@pytest.fixture
def client():
    return app.test_client()

def get_mock_context():
    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=(Mock(), None))
    mock_context.__exit__ = Mock(return_value=None)
    return mock_context

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
