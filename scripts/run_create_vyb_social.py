"""Create vyb_social on RDS and copy social tables from icebreaker."""

import secrets
import string
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TABLES = (
    "user_likes",
    "user_likes_near",
    "session_likes",
    "session_likes_near",
    "wave",
    "waveback",
    "netwirkRequestsAccepted",
    "netwirkRequestsPending",
    "requestTracker",
    "acceptRequestTracker",
    "blockedUsers",
    "netwirkReports",
    "hidden_users",
    "hidden_users_1day",
    "hidden_users_1month",
)


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
    lines = path.read_text(encoding="utf-8").splitlines()
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
    cursor.execute("CREATE DATABASE IF NOT EXISTS vyb_social")
    print("created_database=vyb_social")

    for table in TABLES:
        try:
            cursor.execute("SHOW TABLES FROM icebreaker LIKE %s", (table,))
            if not cursor.fetchone():
                print(f"skip={table} reason=missing_in_icebreaker")
                continue
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS vyb_social.`{table}` LIKE icebreaker.`{table}`"
            )
            cursor.execute(f"SELECT COUNT(*) FROM vyb_social.`{table}`")
            existing = cursor.fetchone()[0]
            if existing:
                print(f"copied={table} rows={existing} action=already_present")
                continue
            cursor.execute(
                f"INSERT INTO vyb_social.`{table}` SELECT * FROM icebreaker.`{table}`"
            )
            cursor.execute(f"SELECT COUNT(*) FROM vyb_social.`{table}`")
            print(f"copied={table} rows={cursor.fetchone()[0]}")
            cursor.execute(
                """
                SELECT AUTO_INCREMENT FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = 'icebreaker' AND TABLE_NAME = %s
                """,
                (table,),
            )
            auto = cursor.fetchone()
            if auto and auto[0]:
                cursor.execute(
                    f"ALTER TABLE vyb_social.`{table}` AUTO_INCREMENT = {int(auto[0])}"
                )
                print(f"aligned={table} auto_increment={int(auto[0])}")
        except mysql.connector.Error as exc:
            print(f"error={table} {exc.errno}")

    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    cursor.execute(
        "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
        ("social_app", "%", password),
    )
    cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s", ("social_app", "%", password))
    cursor.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON vyb_social.* TO %s@%s",
        ("social_app", "%"),
    )
    cursor.execute("FLUSH PRIVILEGES")
    print("granted=social_app on vyb_social")
    cursor.close()
    conn.close()

    verify = mysql.connector.connect(
        host=env["DB_HOST"],
        port=int(env.get("DB_PORT", "3306")),
        user="social_app",
        password=password,
        database="vyb_social",
    )
    vcur = verify.cursor()
    vcur.execute("SELECT COUNT(*) FROM blockedUsers")
    print(f"verify_social_app_blocked_rows={vcur.fetchone()[0]}")
    vcur.close()
    verify.close()

    _upsert_env(
        ENV_PATH,
        {
            "SOCIAL_DB_HOST": env["DB_HOST"],
            "SOCIAL_DB_PORT": env.get("DB_PORT", "3306"),
            "SOCIAL_DB_USER": "social_app",
            "SOCIAL_DB_PASSWORD": password,
            "SOCIAL_DB_NAME": "vyb_social",
            "SOCIAL_SERVICE_URL": env.get("SOCIAL_SERVICE_URL", "http://social:8000"),
        },
    )
    print("updated_local_env=SOCIAL_DB_*")


if __name__ == "__main__":
    main()
