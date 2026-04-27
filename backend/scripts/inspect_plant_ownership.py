"""
Dev / one-off repair helper: print ``users`` and ``plants`` ownership columns.

Use when samples "disappear" after re-login: compare ``owner_id`` / ``created_by``
to ``users.id`` and fix bad rows manually if both point at the wrong account.

Usage (from ``backend/``):

  python scripts/inspect_plant_ownership.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from database import SessionLocal
from models.plant import Plant
from models.user import User


def main() -> None:
    db: Session = SessionLocal()
    try:
        print("users (id, email)")
        for u in db.query(User).order_by(User.id).all():
            print(f"  {u.id}\t{u.email}")
        print()
        print("plants (id, name, owner_id, created_by)")
        for p in db.query(Plant).order_by(Plant.id).all():
            nm = (p.name or "")[:48]
            print(f"  {p.id}\t{nm}\t{p.owner_id}\t{p.created_by}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
