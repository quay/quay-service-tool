import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from spam_detection import database


def _postgres_config(**overrides):
    config = {
        "SPAM_DETECTION_STATE_DB_URI": "postgresql://spam:secret@example.invalid/spam",
        "SPAM_DETECTION_STATE_DB_POOL_MIN": 1,
        "SPAM_DETECTION_STATE_DB_POOL_MAX": 10,
        "SPAM_DETECTION_STATE_DB_LOCK_CONNECTIONS": 2,
    }
    config.update(overrides)
    return config


def test_request_pool_reserves_connections_for_advisory_locks(monkeypatch):
    calls = []

    class RecordingPool:
        def __init__(self, minimum, maximum, uri):
            calls.append((minimum, maximum, uri))

    monkeypatch.setattr(database, "ThreadedConnectionPool", RecordingPool)

    config = _postgres_config()
    database._postgres_pool(config)

    assert calls == [(1, 8, config["SPAM_DETECTION_STATE_DB_URI"])]


@pytest.mark.parametrize(
    "overrides",
    [
        {"SPAM_DETECTION_STATE_DB_POOL_MIN": 0},
        {"SPAM_DETECTION_STATE_DB_LOCK_CONNECTIONS": 0},
        {
            "SPAM_DETECTION_STATE_DB_POOL_MIN": 2,
            "SPAM_DETECTION_STATE_DB_POOL_MAX": 3,
            "SPAM_DETECTION_STATE_DB_LOCK_CONNECTIONS": 2,
        },
    ],
)
def test_invalid_postgres_connection_reservations_are_rejected(overrides):
    with pytest.raises(ValueError, match="invalid spam detection state DB pool"):
        database._postgres_connection_limits(_postgres_config(**overrides))


def test_advisory_lock_waiters_open_only_the_reserved_number_of_sessions(monkeypatch):
    active_connections = 0
    maximum_active_connections = 0
    counter_lock = threading.Lock()
    first_lock_entered = threading.Event()
    release_locks = threading.Event()

    class FakeCursor:
        def execute(self, sql, params):
            return None

        def close(self):
            return None

    class FakeConnection:
        def __init__(self):
            nonlocal active_connections, maximum_active_connections
            with counter_lock:
                active_connections += 1
                maximum_active_connections = max(
                    maximum_active_connections, active_connections
                )

        def cursor(self):
            return FakeCursor()

        def commit(self):
            return None

        def close(self):
            nonlocal active_connections
            with counter_lock:
                active_connections -= 1

    class FakePsycopg:
        @staticmethod
        def connect(uri):
            return FakeConnection()

    monkeypatch.setattr(database, "psycopg2", FakePsycopg)
    config = _postgres_config(SPAM_DETECTION_STATE_DB_LOCK_CONNECTIONS=1)

    def hold_lock(index):
        with database.state_advisory_lock(config, f"lock-{index}"):
            first_lock_entered.set()
            release_locks.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(hold_lock, index) for index in range(4)]
        assert first_lock_entered.wait(timeout=5)
        assert maximum_active_connections == 1
        release_locks.set()
        for future in futures:
            future.result(timeout=5)

    assert maximum_active_connections == 1
    assert active_connections == 0
