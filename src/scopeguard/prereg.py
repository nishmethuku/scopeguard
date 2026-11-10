"""Pre-registration lock: hash the thresholds and the frozen suite before confirmatory runs."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from .core import Scenario

PREREG = "config/prereg.json"
LOCK = "config/prereg.lock.json"


def suite_hash(suite: list[Scenario]) -> str:
    blob = json.dumps([(s.id, s.params) for s in suite], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path: str = PREREG) -> dict:
    with open(path) as f:
        return json.load(f)


def freeze(suite: list[Scenario], prereg_path: str = PREREG, lock_path: str = LOCK) -> dict:
    lock = {"prereg_sha256": file_hash(prereg_path), "suite_sha256": suite_hash(suite), "n_scenarios": len(suite),
            "frozen_at_utc": datetime.now(timezone.utc).isoformat()}
    with open(lock_path, "w") as f:
        json.dump(lock, f, indent=2)
    return lock


def is_confirmatory(suite: list[Scenario], prereg_path: str = PREREG, lock_path: str = LOCK) -> bool:
    """True only if a lock exists and both the prereg file and the suite still match it."""
    if not (os.path.exists(prereg_path) and os.path.exists(lock_path)):
        return False
    with open(lock_path) as f:
        lock = json.load(f)
    return lock.get("prereg_sha256") == file_hash(prereg_path) and lock.get("suite_sha256") == suite_hash(suite)
