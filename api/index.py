import sys
from pathlib import Path

# Project root (one level up from api/)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app  # noqa: F401 – Vercel looks for `app` in this file

__all__ = ["app"]
