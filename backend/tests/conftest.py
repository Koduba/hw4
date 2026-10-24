"""Shared test setup: keep tests away from the real, append-only output/audit_trail.json."""

import os
import tempfile
from pathlib import Path

# Set before any test imports audit.py (it reads AUDIT_PATH at import time).
_AUDIT_DIR = Path(tempfile.mkdtemp(prefix="cc-audit-"))
os.environ["AUDIT_PATH"] = str(_AUDIT_DIR / "audit_trail.json")
