"""Populate .env on EC2 from existing /home/ec2-user/flask-app/sparopt config if present."""

import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
OLD_APP = Path("/home/ec2-user/flask-app/sparopt")


def main():
    env_vars = {
        "JWT_SECRET_KEY": secrets.token_hex(32),
        "DB_PORT": "3306",
        "NETWORK_DB_NAME": "icebreaker",
        "OFFLINE_FEED_CACHE_ENABLED": "true",
        "OFFLINE_FEED_CACHE_TTL": "600",
    }

    old_env = OLD_APP / ".env"
    if old_env.is_file():
        for line in old_env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")

    old_db = OLD_APP / "Model" / "netwirk_DB.py"
    if old_db.is_file():
        text = old_db.read_text(encoding="utf-8", errors="ignore")
        patterns = {
            "DB_HOST": r"""host\s*=\s*['"]([^'"]+)['"]""",
            "DB_USER": r"""user\s*=\s*['"]([^'"]+)['"]""",
            "DB_PASSWORD": r"""password\s*=\s*['"]([^'"]+)['"]""",
            "NETWORK_DB_NAME": r"""database\s*=\s*['"]([^'"]+)['"]""",
        }
        for key, pat in patterns.items():
            m = re.search(pat, text)
            if m and not env_vars.get(key):
                env_vars[key] = m.group(1)

    lines = [f"{k}={v}" for k, v in env_vars.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote .env with keys:", ", ".join(sorted(env_vars.keys())))


if __name__ == "__main__":
    main()
