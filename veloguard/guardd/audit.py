"""Tamper-evident-ish audit trail. Every intent that reaches the guard — allowed,
denied, or approved — lands here as one JSON line. If an AI ever does something
to this box, the answer to 'what and when' lives in this file.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "audit.log"


def record(entry: dict, log_path: Path = DEFAULT_LOG) -> None:
    entry = {"ts": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "pid": os.getpid(), **entry}
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
