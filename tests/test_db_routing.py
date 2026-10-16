from types import SimpleNamespace

import pytest

from Model import db_routing


@pytest.fixture(autouse=True)
def _reset_connection_pools():
    db_routing._POOLS.clear()
    yield
    db_routing._POOLS.clear()


class FakeCursor:
    def __init__(self, *, close_error=None):
        self.close_error = close_error
        self.closed = False
        self.description = ("column",)
        self.rows = [(1,), (2,)]

    def execute(self, operation, params=None, multi=False):
        return operation, params, multi

    def executemany(self, operation, seq_params):
        return operation, seq_params

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error
        return "closed"

    def __iter__(self):
        return iter(self.rows)


class FakeRawConnection:
    def __init__(self, *, connected=True, close_error=None):
        self.connected = connected
        self.close_error = close_error
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.marker = "primary-attribute"
        self.cursors = []

    def cursor(self, *args, **kwargs):
        cursor = FakeCursor()
        cursor.arguments = (args, kwargs)
        self.cursors.append(cursor)
        return cursor

    def is_connected(self):
        return self.connected

    def commit(self):
        self.commits += 1
        return "committed"

    def rollback(self):
        self.rollbacks += 1
        return "rolled back"

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error
        return "connection closed"


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("SELECT 1", "SELECT"),
        ("  show tables", "SHOW"),
        ("/* trace */ EXPLAIN SELECT 1", "EXPLAIN"),
        ("-- comment\nDESCRIBE users", "DESCRIBE"),
        ("/* unterminated", ""),
        ("-- comment only", ""),
        ("", ""),
    ],
)
def test_first_sql_token(statement, expected):
    assert db_routing._first_sql_token(statement) == expected


def make_connection(*, mode="safe", read_host="mysql-read", primary_pinned=False):
    connection = object.__new__(db_routing.RoutingConnection)
    connection._mode = mode
    connection._read_config = {"host": read_host}
    connection._primary_pinned = primary_pinned
    return connection


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO users VALUES (1)",
        "UPDATE users SET active = 1",
        "DELETE FROM users",
        "SELECT * FROM users FOR UPDATE",
        "SELECT GET_LOCK('migration', 1)",
        "SELECT LAST_INSERT_ID()",
        "SELECT @value := 1",
    ],
)
def test_mutating_or_session_sensitive_statements_use_primary(statement, monkeypatch):
    monkeypatch.setattr(db_routing, "_has_flask_safe_request", lambda: True)
    assert make_connection().target_for_statement(statement) == "primary"


def test_safe_get_read_uses_replica(monkeypatch):
    monkeypatch.setattr(db_routing, "_has_flask_safe_request", lambda: True)
    assert make_connection().target_for_statement("SELECT * FROM users") == "read"


def test_safe_non_get_read_uses_primary(monkeypatch):
    monkeypatch.setattr(db_routing, "_has_flask_safe_request", lambda: False)
    assert make_connection().target_for_statement("SELECT * FROM users") == "primary"


def test_all_reads_mode_uses_replica(monkeypatch):
    monkeypatch.setattr(db_routing, "_has_flask_safe_request", lambda: False)
    assert make_connection(mode="all_reads").target_for_statement("SHOW TABLES") == "read"


def test_missing_replica_and_primary_pin_force_primary(monkeypatch):
    monkeypatch.setattr(db_routing, "_has_flask_safe_request", lambda: True)
    assert make_connection(read_host=None).target_for_statement("SELECT 1") == "primary"
    assert make_connection(primary_pinned=True).target_for_statement("SELECT 1") == "primary"


def test_routing_cursor_pins_primary_for_write():
    raw_cursor = SimpleNamespace(execute=lambda *args, **kwargs: "executed")
    connection = SimpleNamespace(
        target_for_statement=lambda operation: "primary",
        pin_primary=lambda: setattr(connection, "pinned", True),
        get_raw_connection=lambda target: SimpleNamespace(cursor=lambda *args, **kwargs: raw_cursor),
        pinned=False,
    )
    cursor = db_routing.RoutingCursor(connection, (), {})

    assert cursor.execute("UPDATE users SET active = 1") == "executed"
    assert connection.pinned is True


def test_routing_connection_initializes_primary_and_lazy_read(monkeypatch):
    created = []

    def connect(**config):
        connection = FakeRawConnection()
        created.append((config, connection))
        return connection

    monkeypatch.setenv("DB_READ_PORT", "3307")
    monkeypatch.setenv("DB_READ_TRAFFIC_MODE", " ALL_READS ")
    monkeypatch.setattr(db_routing.sql, "connect", connect)

    connection = db_routing.RoutingConnection(
        primary_host="mysql-primary",
        read_host="mysql-read",
        port=3306,
        user="app",
        password="secret",
        database="vyb",
    )

    assert len(created) == 1
    assert created[0][0]["host"] == "mysql-primary"
    assert connection._read_config["port"] == 3307
    assert connection._mode == "all_reads"

    read = connection.get_raw_connection("read")
    assert len(created) == 2
    assert created[1][0]["host"] == "mysql-read"
    assert read.autocommit is True
    assert connection.get_raw_connection("read") is read
    assert connection.get_raw_connection("primary") is created[0][1]


def test_disconnected_read_connection_is_replaced(monkeypatch):
    primary = FakeRawConnection()
    replacement = FakeRawConnection()
    monkeypatch.setattr(db_routing.sql, "connect", lambda **config: primary)
    connection = db_routing.RoutingConnection(
        primary_host="mysql-primary",
        read_host="mysql-read",
        port=3306,
        user="app",
        password="secret",
        database="vyb",
    )
    connection._read = FakeRawConnection(connected=False)
    monkeypatch.setattr(db_routing.sql, "connect", lambda **config: replacement)

    assert connection.get_raw_connection("read") is replacement
    assert replacement.autocommit is True


def test_connection_delegates_transaction_cursor_and_attributes(monkeypatch):
    primary = FakeRawConnection()
    monkeypatch.setattr(db_routing.sql, "connect", lambda **config: primary)
    connection = db_routing.RoutingConnection(
        primary_host="mysql-primary",
        port=3306,
        user="app",
        password="secret",
        database="vyb",
    )

    routing_cursor = connection.cursor(dictionary=True)
    assert isinstance(routing_cursor, db_routing.RoutingCursor)
    assert routing_cursor._cursor_kwargs == {"dictionary": True}
    assert connection.commit() == "committed"
    assert connection.rollback() == "rolled back"
    assert connection.marker == "primary-attribute"
    connection.pin_primary()
    assert connection._primary_pinned is True
    assert connection.is_connected() is True
    assert connection.close() is None
    assert primary.closed is False
    assert primary.rollbacks == 2
    assert connection.is_connected() is False
    assert connection.close() is None


def test_connection_status_and_read_close_error(monkeypatch):
    primary = FakeRawConnection(connected=False)
    monkeypatch.setattr(db_routing.sql, "connect", lambda **config: primary)
    connection = db_routing.RoutingConnection(
        primary_host="mysql-primary",
        read_host="mysql-read",
        port=3306,
        user="app",
        password="secret",
        database="vyb",
    )
    connection._read = FakeRawConnection(
        connected=False,
        close_error=RuntimeError("read close failed"),
    )

    assert connection.is_connected() is False
    with pytest.raises(RuntimeError, match="read close failed"):
        connection.close()
    assert primary.closed is True


def test_routing_cursor_lifecycle_and_delegation():
    raw = FakeRawConnection()
    connection = SimpleNamespace(
        target_for_statement=lambda operation: "read",
        pin_primary=lambda: None,
        get_raw_connection=lambda target: raw,
    )
    cursor = db_routing.RoutingCursor(connection, ("buffered",), {"dictionary": True})

    with pytest.raises(AttributeError):
        _ = cursor.description
    assert cursor.close() is None
    assert cursor.execute("SELECT 1", params=(1,)) == ("SELECT 1", (1,), False)
    first_cursor = cursor._cursor
    assert cursor.description == ("column",)
    assert list(cursor) == [(1,), (2,)]

    assert cursor.execute("SELECT 2") == ("SELECT 2", None, False)
    assert first_cursor.closed is True
    assert cursor.executemany("INSERT INTO t VALUES (%s)", [(1,), (2,)]) == (
        "INSERT INTO t VALUES (%s)",
        [(1,), (2,)],
    )
    assert cursor.close() == "closed"

    with db_routing.RoutingCursor(connection, (), {}) as context_cursor:
        context_cursor.execute("SELECT 3")
    assert context_cursor._cursor.closed is True
