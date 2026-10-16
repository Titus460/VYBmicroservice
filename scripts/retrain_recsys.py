#!/usr/bin/env python3
"""
Weekly recsys retrain — backfill interactions, train XGBoost ranker, rebuild FAISS.

Usage (from repo root on EC2):
  source /home/ec2-user/flask-app/env/bin/activate
  cd /home/ec2-user/flask-app/sparopt
  python scripts/retrain_recsys.py

Cron example (Sundays 03:00 UTC):
  0 3 * * 0 cd /home/ec2-user/flask-app/sparopt && /home/ec2-user/flask-app/env/bin/python scripts/retrain_recsys.py >> /var/log/recsys_retrain.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrain offline recsys ranker + FAISS index")
    parser.add_argument("--no-backfill", action="store_true", help="Skip legacy table backfill")
    parser.add_argument("--since-days", type=int, default=None, help="Only use interactions from last N days")
    parser.add_argument("--profile-limit", type=int, default=5000)
    parser.add_argument("--min-samples", type=int, default=20)
    args = parser.parse_args()

    try:
        from Model.netwirk_profile import profile
        from Model.recsys.train import retrain_from_mysql

        svc = profile()
        cursor = svc.db.cur()
        try:
            result = retrain_from_mysql(
                svc,
                cursor,
                backfill_legacy=not args.no_backfill,
                since_days=args.since_days,
                profile_limit=args.profile_limit,
                min_samples=args.min_samples,
            )
            svc.db.conn.commit()
        finally:
            cursor.close()

        print(json.dumps(result, indent=2, default=str))
        trained = result.get("ranker", {}).get("trained", False)
        return 0 if trained or result.get("interactions_loaded", 0) > 0 else 1
    except Exception:
        logging.exception("Recsys retrain failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
