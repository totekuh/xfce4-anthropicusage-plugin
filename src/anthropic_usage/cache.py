"""On-disk cache: last-good usage payload, 429 back-off window, fetch log."""

import json
import os
import time
from datetime import datetime
from typing import Optional, Tuple

from .config import Config


def log_event(cfg: Config, msg: str) -> None:
    """Append one timestamped line to the widget log (best-effort, size-capped)."""
    try:
        os.makedirs(cfg.cache_dir, exist_ok=True)
        try:
            if os.path.getsize(cfg.log_path) > cfg.log_cap:
                with open(cfg.log_path) as f:
                    lines = f.readlines()
                with open(cfg.log_path, "w") as f:
                    f.writelines(lines[len(lines) // 2:])
        except FileNotFoundError:
            pass
        with open(cfg.log_path, "a") as f:
            f.write("%s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def read_backoff(cfg: Config) -> float:
    try:
        with open(cfg.backoff_path) as f:
            return float(f.read().strip())
    except Exception:
        return 0.0


def set_backoff(cfg: Config, secs: float) -> None:
    try:
        os.makedirs(cfg.cache_dir, exist_ok=True)
        with open(cfg.backoff_path, "w") as f:
            f.write(str(time.time() + secs))
    except Exception:
        pass


def clear_backoff(cfg: Config) -> None:
    try:
        os.remove(cfg.backoff_path)
    except OSError:
        pass


def save_cache(cfg: Config, data: dict) -> None:
    os.makedirs(cfg.cache_dir, exist_ok=True)
    payload = {"fetched_at": time.time(), "data": data}
    tmp = cfg.cache_json + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, cfg.cache_json)


def load_cache(cfg: Config) -> Tuple[Optional[dict], float]:
    try:
        with open(cfg.cache_json) as f:
            p = json.load(f)
        return p["data"], p.get("fetched_at", 0)
    except Exception:
        return None, 0
