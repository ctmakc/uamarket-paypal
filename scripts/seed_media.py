#!/usr/bin/env python3
"""Attach the generated demonstration pictures to a catalogue that is already seeded.

`POST /admin/seed-catalog` does this for a fresh shop, but a deployment seeded before
the pictures existed has products and makers without them, and re-seeding changes
nothing there (the seed is insert-only). This walks the live database instead.

    python -m scripts.seed_media            # fill in what is missing
    python -m scripts.seed_media --force    # also rewrite the pictures this script wrote

A photo the owner uploaded in /admin, and a maker picture pointing anywhere else, are
left alone in both modes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import make_engine, make_session_factory  # noqa: E402
from app.services.catalog_media import attach_seed_media  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="replace pictures this script wrote before")
    ap.add_argument("--database-url", default=None, help="default: DATABASE_URL, the same one the API uses")
    args = ap.parse_args()
    session_factory = make_session_factory(make_engine(args.database_url))
    with session_factory() as db:
        result = attach_seed_media(db, force=args.force)
        db.commit()
    print(f"product images: {result['product_images']}, maker images: {result['maker_images']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
