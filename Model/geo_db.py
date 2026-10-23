"""Geo-owned MySQL access: read/write vyb_geo, mirror writes to icebreaker."""

import os
import re

from Model.netwirk_DB import DB

GEO_TABLES = (
    "location",
    "radius",
    "user_latlong",
    "user_live_location",
    "user_live_location_offline",
    "eventLocation",
    "sessiontracker",
)
_WRITE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|REPLACE|ALTER|CREATE|DROP|TRUNCATE)\b",
    re.IGNORECASE,
)


def geo_schema():
    return os.getenv("GEO_DB_NAME") or os.getenv("NETWORK_DB_NAME") or "icebreaker"


def rewrite_geo_sql(sql, schema):
    if not sql or not schema or schema == "icebreaker":
        return sql
    rewritten = sql
    for table in GEO_TABLES:
        rewritten = rewritten.replace(f"icebreaker.{table}", f"{schema}.{table}")
    return rewritten


def is_write_sql(sql):
    return bool(sql and _WRITE.match(sql))


class DualWriteCursor:
    def __init__(self, cursor, schema):
        self._cursor = cursor
        self._schema = schema

    def execute(self, operation, params=None, multi=False):
        rewritten = rewrite_geo_sql(operation, self._schema)
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


class GeoDB(DB):
    def __init__(self):
        super().__init__(env_prefix="GEO")
        self.schema = geo_schema()

    def cur(self):
        return DualWriteCursor(self.conn.cursor(), self.schema)
