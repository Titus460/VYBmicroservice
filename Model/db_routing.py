import os
import re
import threading

import mysql.connector as sql


class _LazyConnectionPool:
    """Reuse open MySQL connections. New connections are created only when the idle set is empty."""

    def __init__(self, config, max_size):
        self._config = dict(config)
        self._max_size = max_size
        self._idle = []
        self._checked_out = 0
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            while self._idle:
                conn = self._idle.pop()
                try:
                    conn.ping(reconnect=True, attempts=1, delay=0)
                    self._checked_out += 1
                    return conn
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
            self._checked_out += 1
        try:
            return sql.connect(**self._config)
        except Exception:
            with self._lock:
                self._checked_out = max(0, self._checked_out - 1)
            raise

    def release(self, conn):
        if conn is None:
            return
        reusable = False
        try:
            conn.rollback()
            reusable = bool(conn.is_connected())
        except Exception:
            reusable = False
        with self._lock:
            self._checked_out = max(0, self._checked_out - 1)
            if reusable and len(self._idle) < self._max_size:
                self._idle.append(conn)
                return None
        return conn.close()


_POOLS = {}
_POOLS_LOCK = threading.Lock()


def _pool_for(config):
    key = (
        config.get("host"),
        config.get("port"),
        config.get("user"),
        config.get("database"),
    )
    with _POOLS_LOCK:
        pool = _POOLS.get(key)
        if pool is None:
            max_size = int(os.environ.get("DB_POOL_SIZE", "8"))
            pool = _LazyConnectionPool(config, max_size)
            _POOLS[key] = pool
        return pool


READ_ONLY_COMMANDS = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")
PRIMARY_ONLY_PATTERNS = (
    re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE),
    re.compile(r"\bLOCK\s+IN\s+SHARE\s+MODE\b", re.IGNORECASE),
    re.compile(r"\bGET_LOCK\s*\(", re.IGNORECASE),
    re.compile(r"\bLAST_INSERT_ID\s*\(", re.IGNORECASE),
    re.compile(r"\bROW_COUNT\s*\(", re.IGNORECASE),
    re.compile(r"\bFOUND_ROWS\s*\(", re.IGNORECASE),
    re.compile(r"@\w+\s*:=", re.IGNORECASE),
)


def _first_sql_token(statement):
    sql_text = statement.strip()
    while True:
        if sql_text.startswith("/*"):
            end = sql_text.find("*/")
            if end == -1:
                return ""
            sql_text = sql_text[end + 2 :].lstrip()
            continue
        if sql_text.startswith("--"):
            end = sql_text.find("\n")
            if end == -1:
                return ""
            sql_text = sql_text[end + 1 :].lstrip()
            continue
        break

    match = re.match(r"([A-Za-z]+)", sql_text)
    return match.group(1).upper() if match else ""


def _has_flask_safe_request():
    try:
        from flask import has_request_context, request

        return has_request_context() and request.method in {"GET", "HEAD", "OPTIONS"}
    except Exception:
        return False


class RoutingCursor:
    def __init__(self, connection, cursor_args, cursor_kwargs):
        self._connection = connection
        self._cursor_args = cursor_args
        self._cursor_kwargs = cursor_kwargs
        self._cursor = None

    def _open_cursor(self, target):
        raw_connection = self._connection.get_raw_connection(target)
        return raw_connection.cursor(*self._cursor_args, **self._cursor_kwargs)

    def execute(self, operation, params=None, multi=False):
        target = self._connection.target_for_statement(operation)
        if target == "primary":
            self._connection.pin_primary()
        if self._cursor is not None:
            try:
                self._cursor.close()
            except Exception:
                pass
        self._cursor = self._open_cursor(target)
        if params is not None:
            return self._cursor.execute(operation, params)
        return self._cursor.execute(operation)

    def executemany(self, operation, seq_params):
        self._connection.pin_primary()
        if self._cursor is not None:
            try:
                self._cursor.close()
            except Exception:
                pass
        self._cursor = self._open_cursor("primary")
        return self._cursor.executemany(operation, seq_params)

    def close(self):
        if self._cursor is not None:
            return self._cursor.close()
        return None

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __getattr__(self, name):
        if self._cursor is None:
            raise AttributeError(name)
        return getattr(self._cursor, name)


class RoutingConnection:
    def __init__(self, *, primary_host, read_host=None, port, user, password, database):
        self._primary_config = {
            "host": primary_host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }
        self._read_config = {
            "host": read_host,
            "port": int(os.environ.get("DB_READ_PORT", str(port))),
            "user": user,
            "password": password,
            "database": database,
        }
        self._mode = os.environ.get("DB_READ_TRAFFIC_MODE", "safe").strip().lower()
        self._primary_pool = _pool_for(self._primary_config)
        self._read_pool = _pool_for(self._read_config) if self._read_config["host"] else None
        self._primary = self._primary_pool.acquire()
        self._read = None
        self._primary_pinned = False
        self._closed = False

    def get_raw_connection(self, target):
        if target == "read" and self._read_pool is not None:
            if self._read is None or not self._read.is_connected():
                if self._read is not None:
                    self._read_pool.release(self._read)
                self._read = self._read_pool.acquire()
                self._read.autocommit = True
            return self._read
        return self._primary

    def target_for_statement(self, operation):
        if self._primary_pinned or not self._read_config["host"]:
            return "primary"
        if not isinstance(operation, str):
            return "primary"

        token = _first_sql_token(operation)
        if token not in READ_ONLY_COMMANDS:
            return "primary"
        if any(pattern.search(operation) for pattern in PRIMARY_ONLY_PATTERNS):
            return "primary"
        if self._mode == "all_reads":
            return "read"
        if self._mode == "safe" and _has_flask_safe_request():
            return "read"
        return "primary"

    def pin_primary(self):
        self._primary_pinned = True

    def cursor(self, *args, **kwargs):
        return RoutingCursor(self, args, kwargs)

    def commit(self):
        return self._primary.commit()

    def rollback(self):
        return self._primary.rollback()

    def close(self):
        if self._closed:
            return None
        self._closed = True
        read_error = None
        if self._read is not None and self._read_pool is not None:
            try:
                self._read_pool.release(self._read)
            except Exception as exc:
                read_error = exc
            self._read = None
        primary = self._primary
        self._primary = None
        primary_result = None
        try:
            if primary is not None:
                primary_result = self._primary_pool.release(primary)
        finally:
            if read_error:
                raise read_error
        return primary_result

    def is_connected(self):
        primary_connected = self._primary is not None and self._primary.is_connected()
        read_connected = self._read is None or self._read.is_connected()
        return primary_connected and read_connected

    def __getattr__(self, name):
        return getattr(self._primary, name)
