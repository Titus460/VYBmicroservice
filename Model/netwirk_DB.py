import os

from Model.db_routing import RoutingConnection


class DB:
    host = os.environ.get('DB_HOST', 'mysql.vyb-database.svc.cluster.local')
    read_host = os.environ.get('DB_READ_HOST', '')
    port = int(os.environ.get('DB_PORT', '3306'))
    user = os.environ.get('DB_USER', '')
    password = os.environ.get('DB_PASSWORD', '')
    database = os.environ.get('NETWORK_DB_NAME', 'icebreaker')

    def __init__(self):
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
