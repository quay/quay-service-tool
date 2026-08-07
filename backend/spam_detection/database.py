import json
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from . import DEFAULT_QUARANTINE_DESCRIPTION


POSTGRES_URI_PREFIXES = ("postgres://", "postgresql://")
IntegrityError = psycopg2.IntegrityError
_SCHEMA_SQL = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
_POSTGRES_POOLS = {}
_POSTGRES_POOLS_LOCK = threading.Lock()
_POSTGRES_LOCK_LIMITERS = {}
_POSTGRES_SCHEMAS_READY = set()
_INITIALIZED_STATE_DBS = set()
_INITIALIZE_LOCK = threading.Lock()


def utcnow():
    return datetime.utcnow().isoformat(timespec="seconds")


def new_uuid():
    return str(uuid.uuid4())


def state_db_uri(config):
    uri = config.get("SPAM_DETECTION_STATE_DB_URI")
    if not uri or not uri.startswith(POSTGRES_URI_PREFIXES):
        raise ValueError("SPAM_DETECTION_STATE_DB_URI must be a PostgreSQL URI")
    return uri


def display_state_db_uri(config):
    return re.sub(r"(://[^:/@]+:)[^@]+@", r"\1***@", state_db_uri(config))


def _postgres_schema(config):
    schema = config.get("SPAM_DETECTION_STATE_DB_SCHEMA") or "public"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("SPAM_DETECTION_STATE_DB_SCHEMA must be a PostgreSQL identifier")
    return schema


def _config_bool(config, key, default=False):
    value = config.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class _PostgresCursor:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class _PostgresConnection:
    def __init__(self, pool, connection):
        self._pool = pool
        self._connection = connection
        self._closed = False

    def execute(self, statement, params=()):
        cursor = self._connection.cursor(cursor_factory=RealDictCursor)
        statement = statement.replace("?", "%s")
        returns_id = bool(
            re.match(r"^\s*INSERT\s+INTO\b", statement, re.IGNORECASE)
            and not re.search(r"\bRETURNING\b", statement, re.IGNORECASE)
        )
        if returns_id:
            statement = f"{statement.rstrip().rstrip(';')} RETURNING id"
        cursor.execute(statement, tuple(params))
        lastrowid = cursor.fetchone()["id"] if returns_id else None
        return _PostgresCursor(cursor, lastrowid=lastrowid)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        if not self._closed:
            self._pool.putconn(self._connection)
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def _postgres_connection_limits(config):
    minimum = int(config.get("SPAM_DETECTION_STATE_DB_POOL_MIN", 1))
    total = int(config.get("SPAM_DETECTION_STATE_DB_POOL_MAX", 10))
    lock_connections = int(config.get("SPAM_DETECTION_STATE_DB_LOCK_CONNECTIONS", 1))
    request_connections = total - lock_connections
    if minimum <= 0 or lock_connections <= 0 or request_connections < minimum:
        raise ValueError("invalid spam detection state DB pool configuration")
    return minimum, request_connections, lock_connections


def _postgres_pool(config):
    uri = state_db_uri(config)
    schema = _postgres_schema(config)
    minimum, request_connections, lock_connections = _postgres_connection_limits(config)
    pool_key = (uri, schema, minimum, request_connections, lock_connections)
    with _POSTGRES_POOLS_LOCK:
        pool = _POSTGRES_POOLS.get(pool_key)
        if pool is None:
            pool = ThreadedConnectionPool(minimum, request_connections, uri)
            _POSTGRES_POOLS[pool_key] = pool
        return pool


def _postgres_lock_limiter(config):
    uri = state_db_uri(config)
    _, _, lock_connections = _postgres_connection_limits(config)
    limiter_key = (uri, lock_connections)
    with _POSTGRES_POOLS_LOCK:
        limiter = _POSTGRES_LOCK_LIMITERS.get(limiter_key)
        if limiter is None:
            limiter = threading.BoundedSemaphore(lock_connections)
            _POSTGRES_LOCK_LIMITERS[limiter_key] = limiter
        return limiter


def connect_state_db(config):
    pool = _postgres_pool(config)
    connection = pool.getconn()
    connection.autocommit = False
    schema = _postgres_schema(config)
    schema_key = (state_db_uri(config), schema)
    try:
        cursor = connection.cursor()
        if schema_key not in _POSTGRES_SCHEMAS_READY and _config_bool(
            config, "SPAM_DETECTION_STATE_DB_CREATE_SCHEMA"
        ):
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            connection.commit()
        cursor.execute(f'SET search_path TO "{schema}"')
        connection.commit()
        _POSTGRES_SCHEMAS_READY.add(schema_key)
        cursor.close()
    except Exception:
        connection.rollback()
        pool.putconn(connection)
        raise
    return _PostgresConnection(pool, connection)


def check_state_db(config):
    with connect_state_db(config) as conn:
        conn.execute("SELECT 1").fetchone()


@contextmanager
def state_transaction(config):
    conn = connect_state_db(config)
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def state_advisory_lock(config, name):
    with _postgres_lock_limiter(config):
        connection = psycopg2.connect(state_db_uri(config))
        cursor = None
        acquired = False
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", (name,))
            acquired = True
            yield
        finally:
            try:
                if acquired:
                    cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", (name,))
                    connection.commit()
            finally:
                if cursor is not None:
                    cursor.close()
                connection.close()


JSON_FIELDS = {"hard_filter_results"}


def row_to_dict(row):
    if row is None:
        return None
    result = dict(row)
    for key, value in list(result.items()):
        if (key.endswith("_json") or key in JSON_FIELDS) and value:
            result[key] = json.loads(value)
    return result


def json_dumps(value):
    return json.dumps(value or {}, sort_keys=True)


def initialize_state_db(config):
    state_key = (state_db_uri(config), _postgres_schema(config))
    if state_key in _INITIALIZED_STATE_DBS:
        return
    with _INITIALIZE_LOCK:
        if state_key in _INITIALIZED_STATE_DBS:
            return
        with connect_state_db(config) as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext(?))",
                ("quay-service-tool-spam-detection-schema",),
            )
            conn.execute(_SCHEMA_SQL)
        _INITIALIZED_STATE_DBS.add(state_key)


def ensure_policy(conn, config):
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext(?))",
        ("quay-service-tool-spam-detection-policy",),
    )
    row = conn.execute("SELECT * FROM spam_policy ORDER BY id LIMIT 1").fetchone()
    if row:
        return row

    now = utcnow()
    conn.execute(
        """
        INSERT INTO spam_policy (
            uuid, scan_threshold, ingress_threshold, include_private,
            public_only_default, scan_empty_repositories_only, scan_filters_json,
            quarantine_description, scan_dry_run, max_repos, batch_size,
            sleep_between_batches, rescan_terminal_records, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_uuid(),
            float(config.get("SPAM_DETECTION_SCAN_THRESHOLD", 0.9)),
            float(config.get("SPAM_DETECTION_INGRESS_THRESHOLD", 0.9)),
            1 if config.get("SPAM_DETECTION_INCLUDE_PRIVATE", False) else 0,
            0 if config.get("SPAM_DETECTION_INCLUDE_PRIVATE", False) else 1,
            1,
            "{}",
            config.get(
                "SPAM_DETECTION_QUARANTINE_DESCRIPTION",
                DEFAULT_QUARANTINE_DESCRIPTION,
            ),
            1 if config.get("SPAM_DETECTION_SCAN_DRY_RUN", True) else 0,
            int(config.get("SPAM_DETECTION_MAX_REPOS", 0)),
            int(config.get("SPAM_DETECTION_BATCH_SIZE", 200)),
            float(config.get("SPAM_DETECTION_SLEEP_BETWEEN_BATCHES", 0.5)),
            1 if config.get("SPAM_DETECTION_RESCAN_TERMINAL_RECORDS", False) else 0,
            now,
            now,
        ),
    )
    return conn.execute("SELECT * FROM spam_policy ORDER BY id LIMIT 1").fetchone()
