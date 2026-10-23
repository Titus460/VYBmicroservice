"""Create vyb_auth on the current RDS and copy auth tables from icebreaker.

Reads DB_* from .env. Writes AUTH_DB_* into .env. Does not drop icebreaker tables.
"""

import secrets
import string
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TABLES = ("registration", "otp_store", "phone_otp_store", "AppleRegistration")


def _load_env(path):
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _upsert_env(path, updates):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    keys_written = set()
    new_lines = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.strip().startswith("#") else None
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            keys_written.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in keys_written:
            new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main():
    env = _load_env(ENV_PATH)
    conn = mysql.connector.connect(
        host=env["DB_HOST"],
        port=int(env.get("DB_PORT", "3306")),
        user=env["DB_USER"],
        password=env["DB_PASSWORD"],
    )
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS vyb_auth")
    print("created_database=vyb_auth")

    for table in TABLES:
        try:
            cursor.execute("SHOW TABLES FROM icebreaker LIKE %s", (table,))
            if not cursor.fetchone():
                print(f"skip={table} reason=missing_in_icebreaker")
                continue
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS vyb_auth.`{table}` LIKE icebreaker.`{table}`"
            )
            cursor.execute(f"SELECT COUNT(*) FROM vyb_auth.`{table}`")
            existing = cursor.fetchone()[0]
            if existing:
                print(f"copied={table} rows={existing} action=already_present")
                continue
            cursor.execute(
                f"INSERT INTO vyb_auth.`{table}` SELECT * FROM icebreaker.`{table}`"
            )
            cursor.execute(f"SELECT COUNT(*) FROM vyb_auth.`{table}`")
            print(f"copied={table} rows={cursor.fetchone()[0]}")
        except mysql.connector.Error as exc:
            print(f"error={table} {exc.errno}")

    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    cursor.execute(
        "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
        ("auth_app", "%", password),
    )
    cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s", ("auth_app", "%", password))
    cursor.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON vyb_auth.* TO %s@%s",
        ("auth_app", "%"),
    )
    cursor.execute("FLUSH PRIVILEGES")
    print("granted=auth_app on vyb_auth")
    cursor.close()
    conn.close()

    verify = mysql.connector.connect(
        host=env["DB_HOST"],
        port=int(env.get("DB_PORT", "3306")),
        user="auth_app",
        password=password,
        database="vyb_auth",
    )
    vcur = verify.cursor()
    vcur.execute("SELECT COUNT(*) FROM registration")
    print(f"verify_auth_app_registration_rows={vcur.fetchone()[0]}")
    vcur.close()
    verify.close()

    _upsert_env(
        ENV_PATH,
        {
            "AUTH_DB_HOST": env["DB_HOST"],
            "AUTH_DB_PORT": env.get("DB_PORT", "3306"),
            "AUTH_DB_USER": "auth_app",
            "AUTH_DB_PASSWORD": password,
            "AUTH_DB_NAME": "vyb_auth",
            "AUTH_SERVICE_URL": env.get("AUTH_SERVICE_URL", "http://auth:8000"),
        },
    )
    print("updated_local_env=AUTH_DB_*")


if __name__ == "__main__":
    main()
