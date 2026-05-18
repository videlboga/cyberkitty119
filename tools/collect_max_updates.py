"""Simple MAX updates collector.

Polls Max API using the project's MaxAPI client and appends raw updates
(one JSON object per line) to data/max_all_updates.log with a timestamp.

Run inside the container with PYTHONPATH=/app.
"""

import time
import json
import os
from datetime import datetime

from max_bot.api_client import MaxAPI

OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "max_all_updates.log")


def write_line(obj):
    try:
        with open(OUT_PATH, "a", encoding="utf-8") as fh:
            line = json.dumps({"ts": datetime.utcnow().isoformat(), "update": obj}, ensure_ascii=False)
            fh.write(line + "\n")
    except Exception as exc:
        print("Failed to write update:", exc)


def run_loop():
    api = MaxAPI()
    last_id = None
    print("Collector started, writing to:", OUT_PATH)
    while True:
        try:
            updates = api.get_updates(offset=(last_id + 1 if last_id is not None else None), timeout=30, limit=100)
            if updates:
                for u in updates:
                    try:
                        write_line(u)
                    except Exception:
                        pass
                    # advance last_id based on update id when present
                    uid = u.get("id") or u.get("update_id")
                    if uid is not None:
                        try:
                            last_id = max(last_id or 0, uid)
                        except Exception:
                            last_id = uid
            else:
                # no updates; continue longpoll
                pass
        except Exception as exc:
            print("Collector error:", exc)
            time.sleep(5)


if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        print("Collector stopped by user")
