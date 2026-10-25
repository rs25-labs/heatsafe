"""Vercel entry point: serves the existing FastAPI app as one Python Function."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
# Only /tmp is writable on Vercel; shade computed at runtime is cached there.
os.environ.setdefault("HEATSAFE_CACHE_DIR", "/tmp/heatsafe-cache")

from heatsafe.api import app

__all__ = ["app"]
