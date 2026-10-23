"""Auth-owned MySQL access: read/write vyb_auth, mirror writes to icebreaker."""

import os
import re

from Model.netwirk_DB import DB

AUTH_TABLES = ("registration", "otp_store", "phone_otp_store", "AppleRegistration")
_WRITE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|REPLACE|ALTER|CREATE|DROP|TRUNCATE)\b",
    re.IGNORECASE,
)


def auth_schema():
    return os.getenv("AUTH_DB_NAME") or os.getenv("NETWORK_DB_NAME") or "icebreaker"


def rewrite_auth_sql(sql, schema):
    if not sql or not schema or schema == "icebreaker":
        return sql
    rewritten = sql
    for table in AUTH_TABLES:
        rewritten = rewritten.replace(f"icebreaker.{table}", f"{schema}.{table}")
    return rewritten


def is_write_sql(sql):
    return bool(sql and _WRITE.match(sql))


class DualWriteCursor:
    def __init__(self, cursor, schema):
        self._cursor = cursor
        self._schema = schema

    def execute(self, operation, params=None, multi=False):
        rewritten = rewrite_auth_sql(operation, self._schema)
        if params is None:
            result = self._cursor.execute(rewritten)
        else:
            result = self._cursor.execute(rewritten, params)
        if (
            self._schema != "icebreaker"
            and rewritten != operation
            and is_write_sql(operation)
        ):
            if params is None:
                self._cursor.execute(operation)
            else:
                self._cursor.execute(operation, params)
        return result

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class AuthDB(DB):
    def __init__(self):
        super().__init__(env_prefix="AUTH")
        self.schema = auth_schema()

    def cur(self):
        return DualWriteCursor(self.conn.cursor(), self.schema)
