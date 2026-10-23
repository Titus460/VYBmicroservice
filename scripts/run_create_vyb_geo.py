"""Create vyb_geo on RDS and copy geo tables from icebreaker."""

import secrets
import string
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TABLES = (
    "location",
    "radius",
    "user_latlong",
    "user_live_location",
    "user_live_location_offline",
    "eventLocation",
    "sessiontracker",
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
    cursor.execute("CREATE DATABASE IF NOT EXISTS vyb_geo")
    print("created_database=vyb_geo")

    for table in TABLES:
        try:
            cursor.execute("SHOW TABLES FROM icebreaker LIKE %s", (table,))
            if not cursor.fetchone():
                print(f"skip={table} reason=missing_in_icebreaker")
                continue
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS vyb_geo.`{table}` LIKE icebreaker.`{table}`"
            )
            cursor.execute(f"SELECT COUNT(*) FROM vyb_geo.`{table}`")
            existing = cursor.fetchone()[0]
            if existing:
                print(f"copied={table} rows={existing} action=already_present")
                continue
            cursor.execute(
                f"INSERT INTO vyb_geo.`{table}` SELECT * FROM icebreaker.`{table}`"
            )
            cursor.execute(f"SELECT COUNT(*) FROM vyb_geo.`{table}`")
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
                    f"ALTER TABLE vyb_geo.`{table}` AUTO_INCREMENT = {int(auto[0])}"
                )
                print(f"aligned={table} auto_increment={int(auto[0])}")
        except mysql.connector.Error as exc:
            print(f"error={table} {exc.errno}")

    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    cursor.execute(
        "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
        ("geo_app", "%", password),
    )
    cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s", ("geo_app", "%", password))
    cursor.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON vyb_geo.* TO %s@%s",
        ("geo_app", "%"),
    )
    # Dual-write mirrors owned tables back to icebreaker; JOINs still read other modules there.
    cursor.execute("GRANT SELECT ON icebreaker.* TO %s@%s", ("geo_app", "%"))
    for table in TABLES:
        try:
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON icebreaker.`{table}` TO %s@%s",
                ("geo_app", "%"),
            )
        except mysql.connector.Error as exc:
            print(f"grant_icebreaker={table} {exc.errno}")
    cursor.execute("FLUSH PRIVILEGES")
    print("granted=geo_app on vyb_geo")
    cursor.close()
    conn.close()

    verify = mysql.connector.connect(
        host=env["DB_HOST"],
        port=int(env.get("DB_PORT", "3306")),
        user="geo_app",
        password=password,
        database="vyb_geo",
    )
    vcur = verify.cursor()
    vcur.execute("SELECT COUNT(*) FROM location")
    print(f"verify_geo_app_location_rows={vcur.fetchone()[0]}")
    vcur.close()
    verify.close()

    _upsert_env(
        ENV_PATH,
        {
            "GEO_DB_HOST": env["DB_HOST"],
            "GEO_DB_PORT": env.get("DB_PORT", "3306"),
            "GEO_DB_USER": "geo_app",
            "GEO_DB_PASSWORD": password,
            "GEO_DB_NAME": "vyb_geo",
            "GEO_SERVICE_URL": env.get("GEO_SERVICE_URL", "http://geo:8000"),
        },
    )
    print("updated_local_env=GEO_DB_*")


if __name__ == "__main__":
    main()
