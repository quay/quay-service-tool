from contextlib import contextmanager

from playhouse.db_url import connect


class QuayDBError(Exception):
    pass


def _connect(uri):
    if not uri:
        raise QuayDBError("Quay DB URI is not configured")
    db = connect(uri)
    db.connect(reuse_if_open=True)
    return db


@contextmanager
def readonly_db(config):
    uri = config.get("SPAM_DETECTION_READONLY_DB_URI") or config.get("DB_URI")
    db = _connect(uri)
    try:
        yield db
    finally:
        if not db.is_closed():
            db.close()


@contextmanager
def write_db(config):
    uri = config.get("SPAM_DETECTION_WRITE_DB_URI") or config.get("DB_URI")
    db = _connect(uri)
    try:
        yield db
    finally:
        if not db.is_closed():
            db.close()


def check_connection(uri):
    db = _connect(uri)
    try:
        db.execute_sql("SELECT 1")
    finally:
        if not db.is_closed():
            db.close()


def _quote(db, name):
    if "mysql" in db.__class__.__name__.lower():
        return f"`{name}`"
    return f'"{name}"'


def fetch_repository_batch(db, last_seen_id=0, batch_size=200, include_private=False, empty_only=False):
    param = db.param
    repository_table = _quote(db, "repository")
    user_table = _quote(db, "user")
    visibility_table = _quote(db, "visibility")
    tag_table = _quote(db, "tag")

    where = [
        f"r.id > {param}",
        f"r.state = {param}",
        "r.description IS NOT NULL",
        "r.description != ''",
    ]
    where_params = [last_seen_id, 0]
    if not include_private:
        where.append(f"v.name = {param}")
        where_params.append("public")

    active_tag_exists = (
        f"EXISTS (SELECT 1 FROM {tag_table} t "
        f"WHERE t.repository_id = r.id AND t.lifetime_end_ms IS NULL "
        f"AND t.hidden = {param} LIMIT 1)"
    )
    if empty_only:
        where.append(f"NOT {active_tag_exists}")
        where_params.append(False)
    is_empty_expr = f"CASE WHEN {active_tag_exists} THEN 0 ELSE 1 END"
    params = [False] + where_params

    sql = f"""
        SELECT
            r.id,
            u.username AS namespace_name,
            r.name AS repository_name,
            r.description,
            v.name AS visibility,
            {is_empty_expr} AS is_empty
        FROM {repository_table} r
        JOIN {user_table} u ON r.namespace_user_id = u.id
        JOIN {visibility_table} v ON r.visibility_id = v.id
        WHERE {" AND ".join(where)}
        ORDER BY r.id
        LIMIT {param}
    """
    params.append(batch_size)
    cursor = db.execute_sql(sql, tuple(params))
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def update_repository_description(db, repository_id, description):
    param = db.param
    repository_table = _quote(db, "repository")
    sql = f"UPDATE {repository_table} SET description = {param} WHERE id = {param}"
    cursor = db.execute_sql(sql, (description, repository_id))
    return cursor.rowcount
