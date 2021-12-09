from unittest.mock import Mock, patch, call, PropertyMock
from app import app
import pytest as pytest


@pytest.fixture
def client():
    return app.test_client()


class TestUserGet:

    @patch('pymysql.connect')
    def test_return_user(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone.return_value = {"username": "test", "enabled": False}
        res = client.get('/user/test')
        mock_connect().cursor().__enter__().execute.assert_called_with(
            """SELECT username, enabled FROM `user` WHERE username=%s""", ('test',))
        assert res.status_code == 200
        assert res.data == b'{"username": "test", "enabled": false}'

    @patch('pymysql.connect')
    def test_user_not_found(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone.return_value = None
        res = client.get('/user/test')
        mock_connect().cursor().__enter__().execute.assert_called_with(
            """SELECT username, enabled FROM `user` WHERE username=%s""",('test',))
        assert res.status_code == 404
        assert res.data == b'{"message": "Could not find user test"}'

    @patch('pymysql.connect')
    def test_error_during_get(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone = Mock(side_effect=RuntimeError())
        res = client.get('/user/test')
        assert res.status_code == 500
        assert res.data == b'{"message": "Unable to fetch user test"}'


class TestUserPut:
    @patch('pymysql.connect')
    def test_enable_user(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone.return_value = {"id": 1, "username": "test", "enabled": False}
        res = client.put('/user/test?enable=true')
        mock_connect().cursor().__enter__().execute.assert_has_calls([
            call(
                """SELECT username, enabled, id FROM `user` WHERE username=%s""", ('test',)),
            call("""UPDATE `user` SET enabled=%s WHERE username=%s""", (True, 'test'))
        ])
        assert res.status_code == 200
        assert res.data == b'{"message": "User updated successfully", "user": "test", "enabled": true}'

    @patch('pymysql.connect')
    def test_disable_user(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone.return_value = {"id": 1, "username": "test", "enabled": True}
        mock_connect().cursor().__enter__().fetchall.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
        res = client.put('/user/test?enable=false')
        mock_connect().cursor().__enter__().execute.assert_has_calls([
            call(
                """SELECT username, enabled, id FROM `user` WHERE username=%s""",('test',)),
            call("""UPDATE `user` SET enabled=%s WHERE username=%s""",(False,'test')),
            call('SELECT id FROM repository WHERE namespace_user_id=%s', (1,)),
            call('DELETE FROM repositorybuild WHERE repository_id IN (1, 2, 3)'),
            call('DELETE FROM repositorybuildtrigger WHERE repository_id IN (1, 2, 3)'),
            call('DELETE FROM repomirrorconfig WHERE repository_id IN (1, 2, 3)'),
            call('DELETE FROM queueitem WHERE queue_name LIKE %s',('dockerfilebuild/test/%',))
        ])
        mock_connect().commit.assert_called_once()
        assert res.data == b'{"message": "User updated successfully", "user": "test", "enabled": false}'
        assert res.status_code == 200


    @patch('pymysql.connect')
    def test_error(self, mock_connect, client):
        mock_connect().cursor().__enter__().execute = Mock(side_effect=RuntimeError())
        res = client.put('/user/test?enable=false')
        assert res.status_code == 500
        assert res.data == b'{"message": "Unable to update enable status"}'

    @patch('pymysql.connect')
    def test_missing_parameters(self,  mock_connect, client):
        res = client.put('/user/test')
        assert res.status_code == 400
        assert res.data == b'{"message": "Parameter \'enable\' required"}'

    @patch('pymysql.connect')
    def test_user_not_found(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone.return_value = None
        res = client.put('/user/test?enable=true')
        mock_connect().cursor().__enter__().execute.assert_called_with(
            """SELECT username, enabled, id FROM `user` WHERE username=%s""",('test',))
        assert res.status_code == 404
        assert res.data == b'{"message": "Could not find user test"}'

    @patch('pymysql.connect')
    def test_user_already_enabled(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone.return_value = {"username": "test", "enabled": True}
        res = client.put('/user/test?enable=true')
        mock_connect().cursor().__enter__().execute.assert_called_with(
            """SELECT username, enabled, id FROM `user` WHERE username=%s""",('test',))
        assert res.status_code == 400
        assert res.data == b'{"message": "User test already enabled"}'

    @patch('pymysql.connect')
    def test_user_already_disabled(self, mock_connect, client):
        mock_connect().cursor().__enter__().fetchone.return_value = {"username": "test", "enabled": False}
        res = client.put('/user/test?enable=false&queue=testqueue')
        mock_connect().cursor().__enter__().execute.assert_called_with(
            """SELECT username, enabled, id FROM `user` WHERE username=%s""",('test',))
        assert res.status_code == 400
        assert res.data == b'{"message": "User test already disabled"}'
