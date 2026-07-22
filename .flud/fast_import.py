#!/usr/bin/env python3
"""
fast_import.py — Bulk import all titles from movies.db into flud.db without TMDB API calls.

Imports page_url, image_path (poster), and media_type directly.
Titles are derived from URL slugs. Run TMDB enrichment later to add ratings/synopsis.

Usage:
    python3 fast_import.py --provider fmovies
    python3 fast_import.py --provider fmovies --source-db /path/to/movies.db --db /path/to/flud.db
"""

import argparse
import re
import sqlite3
import uuid
from pathlib import Path

DEFAULT_SOURCE_DB = Path(__file__).parent / "movies.db"
DEFAULT_FLUD_DB = Path.home() / "Library" / "Application Support" / "flud" / "flud.db"

BATCH_SIZE = 500


def extract_slug(page_url: str) -> str:
    return page_url.rstrip('/').split('/')[-1]


def slug_to_title(slug: str) -> tuple[str, int | None]:
    """Parse slug into (human_title, season_number)."""
    slug = re.sub(r'-\d+$', '', slug)
    season_match = re.search(r'-season-(\d+)', slug, re.IGNORECASE)
    season_number = int(season_match.group(1)) if season_match else None
    if season_match:
        slug = slug[:season_match.start()]
    title = slug.replace('-', ' ').title()
    return title, season_number


def run(provider_id: str, source_db: Path, flud_db: Path):
    conn = sqlite3.connect(str(flud_db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Verify provider exists
    cur.execute("SELECT id FROM providers WHERE id = ?", (provider_id,))
    if not cur.fetchone():
        print(f"ERROR: Provider '{provider_id}' not found in {flud_db}")
        print("  Launch the app once so providers are loaded from core/providers/*/config.toml")
        conn.close()
        return

    # Load already-processed URLs for idempotency
    cur.execute("SELECT page_url FROM provider_content WHERE provider_id = ?", (provider_id,))
    already_done = {row["page_url"] for row in cur.fetchall()}
    print(f"Skipping {len(already_done)} already-processed URLs.")

    # Load source records
    src_conn = sqlite3.connect(str(source_db))
    src_cur = src_conn.cursor()
    src_cur.execute("SELECT page_url, image_path, media_type FROM movies")
    rows = [r for r in src_cur.fetchall() if r[0] not in already_done]
    src_conn.close()
    print(f"Importing {len(rows)} records from {source_db}...")

    inserted = 0
    skipped = 0

    for i, (page_url, image_path, media_type) in enumerate(rows, 1):
        slug = extract_slug(page_url)
        title, season_number = slug_to_title(slug)

        content_id = str(uuid.uuid4())
        cur.execute(
            """INSERT OR IGNORE INTO content
               (id, tmdb_id, title, media_type, poster_url)
               VALUES (?, NULL, ?, ?, ?)""",
            (content_id, title, media_type, image_path),
        )

        if cur.rowcount == 0:
            # content row already existed (duplicate title from prior run) — look it up
            # We still need a content_id to link provider_content; use a title+type match
            cur.execute(
                "SELECT id FROM content WHERE title = ? AND media_type = ? AND tmdb_id IS NULL LIMIT 1",
                (title, media_type),
            )
            row = cur.fetchone()
            if row:
                content_id = row["id"]
            else:
                skipped += 1
                continue

        cur.execute(
            """INSERT OR IGNORE INTO provider_content
               (id, content_id, provider_id, page_url, season_number)
               VALUES (?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), content_id, provider_id, page_url, season_number),
        )
        inserted += 1

        if i % BATCH_SIZE == 0:
            conn.commit()
            print(f"  [{i}/{len(rows)}] inserted={inserted} skipped={skipped}")

    conn.commit()
    conn.close()
    print(f"\nDone. inserted={inserted} skipped={skipped}")
    print(f"Results written to {flud_db}")
    print("\nRestart the app — Movies and TV Shows tabs will now show all titles.")
    print("Run enrich.py later to add TMDB ratings, synopsis, and posters.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast bulk import from movies.db into flud.db")
    parser.add_argument("--provider", required=True, help="Provider ID (e.g. fmovies)")
    parser.add_argument("--source-db", default=str(DEFAULT_SOURCE_DB), help="Path to movies.db")
    parser.add_argument("--db", default=str(DEFAULT_FLUD_DB), help="Path to flud.db")
    args = parser.parse_args()

    run(
        provider_id=args.provider,
        source_db=Path(args.source_db),
        flud_db=Path(args.db),
    )
