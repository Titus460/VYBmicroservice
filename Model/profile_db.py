"""Profile-owned MySQL access: read/write vyb_profile, mirror writes to icebreaker."""

import os
import re

from Model.netwirk_DB import DB

PROFILE_TABLES = (
    "profile",
    "userPictures",
    "notifications",
    "vibe_I_bring",
    "vibing",
    "vibepersonalityqns3",
    "vibepersonalityqns4",
    "incognito_history",
    "incognito_visibility_exceptions",
    "account_deletion_reasons",
    "Country",
    "user_notification_log",
)
_WRITE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|REPLACE|ALTER|CREATE|DROP|TRUNCATE)\b",
    re.IGNORECASE,
)


def profile_schema():
    return os.getenv("PROFILE_DB_NAME") or os.getenv("NETWORK_DB_NAME") or "icebreaker"


def rewrite_profile_sql(sql, schema):
    if not sql or not schema or schema == "icebreaker":
        return sql
    rewritten = sql
    for table in PROFILE_TABLES:
        rewritten = rewritten.replace(f"icebreaker.{table}", f"{schema}.{table}")
    return rewritten


def is_write_sql(sql):
    return bool(sql and _WRITE.match(sql))


class DualWriteCursor:
    def __init__(self, cursor, schema):
        self._cursor = cursor
        self._schema = schema

    def execute(self, operation, params=None, multi=False):
        rewritten = rewrite_profile_sql(operation, self._schema)
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


class ProfileDB(DB):
    def __init__(self):
        super().__init__(env_prefix="PROFILE")
        self.schema = profile_schema()

    def cur(self):
        return DualWriteCursor(self.conn.cursor(), self.schema)
