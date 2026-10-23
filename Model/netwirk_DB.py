import os

from Model.db_routing import RoutingConnection


class DB:
    """MySQL connection. Optional env_prefix='AUTH' reads AUTH_DB_* first, then DB_*."""

    def __init__(self, env_prefix=""):
        def pick(name, default="", fallback=None):
            if env_prefix:
                prefixed = os.environ.get(f"{env_prefix}_{name}")
                if prefixed:
                    return prefixed
            return os.environ.get(fallback or name, default)

        self.host = pick("DB_HOST", "mysql.vyb-database.svc.cluster.local")
        self.read_host = pick("DB_READ_HOST", "")
        self.port = int(pick("DB_PORT", "3306"))
        self.user = pick("DB_USER", "")
        self.password = pick("DB_PASSWORD", "")
        self.database = pick("DB_NAME", "icebreaker", fallback="NETWORK_DB_NAME")
        self.conn = RoutingConnection(
            primary_host=self.host,
            read_host=self.read_host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
        )

    def cur(self):
        return self.conn.cursor()
