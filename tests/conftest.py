"""Ensure ``import config`` / backend package resolves when pytest runs from repo root."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
