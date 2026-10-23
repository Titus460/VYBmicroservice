"""Set vyb_auth AUTO_INCREMENT to match icebreaker so new userIds stay in sync."""

from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("registration", "otp_store", "phone_otp_store", "AppleRegistration")


def _load_env():
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main():
    env = _load_env()
    conn = mysql.connector.connect(
        host=env["DB_HOST"],
        port=int(env.get("DB_PORT", "3306")),
        user=env["DB_USER"],
        password=env["DB_PASSWORD"],
    )
    conn.autocommit = True
    cursor = conn.cursor()
    for table in TABLES:
        cursor.execute(
            """
            SELECT AUTO_INCREMENT FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = 'icebreaker' AND TABLE_NAME = %s
            """,
            (table,),
        )
        row = cursor.fetchone()
        if not row or row[0] is None:
            print(f"skip={table} reason=no_auto_increment")
            continue
        cursor.execute(
            f"ALTER TABLE vyb_auth.`{table}` AUTO_INCREMENT = {int(row[0])}"
        )
        print(f"aligned={table} auto_increment={int(row[0])}")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
