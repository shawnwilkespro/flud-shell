#!/usr/bin/env python3
"""
enrich.py — TMDB enrichment for flud provider catalog

Reads slug URLs from movies.db (scraped sitemap), matches via TMDB,
and writes enriched content + provider_content rows into flud.db.

Usage:
    python3 enrich.py --provider fmovies --tmdb-key YOUR_KEY
    python3 enrich.py --provider fmovies --tmdb-key YOUR_KEY --db /path/to/flud.db
"""

import argparse
import re
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from difflib import SequenceMatcher

import requests

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
CONFIDENCE_THRESHOLD = 0.80
MAX_WORKERS = 8
REQUEST_DELAY = 0.03  # ~33 req/s — safe under TMDB 40/s limit

DEFAULT_SOURCE_DB = Path(__file__).parent / "movies.db"
DEFAULT_FLUD_DB = Path.home() / "Library" / "Application Support" / "flud" / "flud.db"


def slug_to_title(slug: str) -> tuple[str, int | None]:
    """
    Parse a URL slug into (human_title, season_number).

    Examples:
      'the-dark-knight-1234567'       -> ('The Dark Knight', None)
      'breaking-bad-season-2-1234567' -> ('Breaking Bad', 2)
      'game-of-thrones-season-8-9999' -> ('Game of Thrones', 8)
    """
    # Strip trailing numeric ID (the fmovies suffix)
    slug = re.sub(r'-\d+$', '', slug)

    # Extract and strip season number
    season_match = re.search(r'-season-(\d+)', slug, re.IGNORECASE)
    season_number = int(season_match.group(1)) if season_match else None
    if season_match:
        slug = slug[:season_match.start()]

    # Convert hyphens to spaces and title-case
    title = slug.replace('-', ' ').title()
    return title, season_number


def extract_slug(page_url: str) -> str:
    """Extract slug from URL: 'https://fmoviess.org/film/the-dark-knight-123/' -> 'the-dark-knight-123'"""
    return page_url.rstrip('/').split('/')[-1]


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search_tmdb(title: str, media_type: str, api_key: str) -> dict | None:
    """Search TMDB for a title. Returns enriched dict or None if no confident match."""
    endpoint = "movie" if media_type == "movie" else "tv"
    try:
        r = requests.get(
            f"{TMDB_BASE}/search/{endpoint}",
            params={"query": title, "api_key": api_key},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None

        top = results[0]
        tmdb_title = top.get("title") or top.get("name", "")
        score = title_similarity(title, tmdb_title)

        if score < CONFIDENCE_THRESHOLD:
            return None

        release = top.get("release_date") or top.get("first_air_date") or ""
        year = int(release[:4]) if len(release) >= 4 and release[:4].isdigit() else None
        poster = top.get("poster_path")

        return {
            "tmdb_id": top["id"],
            "title": tmdb_title,
            "synopsis": top.get("overview") or None,
            "poster_url": f"{TMDB_IMAGE_BASE}{poster}" if poster else None,
            "year": year,
            "rating": top.get("vote_average") or None,
        }
    except Exception as e:
        print(f"  TMDB error for '{title}': {e}")
        return None


def enrich_record(row: tuple, provider_id: str, api_key: str, delay: float) -> dict:
    """
    Process one row from movies.db.
    Returns a dict with keys: page_url, title, media_type, season_number, tmdb_data (or None)
    """
    page_url, image_path, media_type = row
    slug = extract_slug(page_url)
    title, season_number = slug_to_title(slug)

    time.sleep(delay)
    tmdb = search_tmdb(title, media_type, api_key)

    return {
        "page_url": page_url,
        "fallback_title": title,
        "fallback_poster": image_path,
        "media_type": media_type,
        "season_number": season_number,
        "tmdb": tmdb,
    }


def run(provider_id: str, api_key: str, source_db: Path, flud_db: Path):
    # Verify provider exists in flud.db
    conn = sqlite3.connect(str(flud_db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id FROM providers WHERE id = ?", (provider_id,))
    if not cur.fetchone():
        print(f"ERROR: Provider '{provider_id}' not found in {flud_db}")
        print("  Run the app once so providers are loaded from core/providers/*/config.toml")
        conn.close()
        return

    # Load already-processed URLs to allow safe re-runs
    cur.execute("SELECT page_url FROM provider_content WHERE provider_id = ?", (provider_id,))
    already_done = {row["page_url"] for row in cur.fetchall()}
    print(f"Skipping {len(already_done)} already-processed URLs.")

    # Load source records
    src_conn = sqlite3.connect(str(source_db))
    src_cur = src_conn.cursor()
    src_cur.execute("SELECT page_url, image_path, media_type FROM movies")
    rows = [r for r in src_cur.fetchall() if r[0] not in already_done]
    src_conn.close()
    print(f"Processing {len(rows)} new records from {source_db}...")

    matched = 0
    unmatched = 0
    errors = 0
    delay_per_worker = REQUEST_DELAY * MAX_WORKERS

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(enrich_record, row, provider_id, api_key, delay_per_worker): row
            for row in rows
        }

        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
            except Exception as e:
                errors += 1
                print(f"  [{i}/{len(rows)}] ERROR: {e}")
                continue

            tmdb = result["tmdb"]
            page_url = result["page_url"]
            media_type = result["media_type"]
            season_number = result["season_number"]

            if tmdb:
                # Try to find existing content row by tmdb_id
                cur.execute("SELECT id FROM content WHERE tmdb_id = ?", (tmdb["tmdb_id"],))
                existing = cur.fetchone()

                if existing:
                    content_id = existing["id"]
                else:
                    content_id = str(uuid.uuid4())
                    cur.execute(
                        """INSERT OR IGNORE INTO content
                           (id, tmdb_id, title, media_type, synopsis, poster_url, year, rating)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            content_id,
                            tmdb["tmdb_id"],
                            tmdb["title"],
                            media_type,
                            tmdb["synopsis"],
                            tmdb["poster_url"],
                            tmdb["year"],
                            tmdb["rating"],
                        ),
                    )
                matched += 1
            else:
                # No TMDB match — store with slug-derived title, no tmdb_id
                content_id = str(uuid.uuid4())
                cur.execute(
                    """INSERT OR IGNORE INTO content
                       (id, tmdb_id, title, media_type, poster_url)
                       VALUES (?, NULL, ?, ?, ?)""",
                    (
                        content_id,
                        result["fallback_title"],
                        media_type,
                        result["fallback_poster"],
                    ),
                )
                unmatched += 1

            # Insert provider_content link
            cur.execute(
                """INSERT OR IGNORE INTO provider_content
                   (id, content_id, provider_id, page_url, season_number)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), content_id, provider_id, page_url, season_number),
            )

            # Commit in batches of 100
            if i % 100 == 0:
                conn.commit()
                print(f"  [{i}/{len(rows)}] matched={matched} unmatched={unmatched} errors={errors}")

    conn.commit()
    conn.close()

    print(f"\nDone. matched={matched} unmatched={unmatched} errors={errors}")
    print(f"Results written to {flud_db}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich flud catalog from TMDB")
    parser.add_argument("--provider", required=True, help="Provider ID (e.g. fmovies)")
    parser.add_argument("--tmdb-key", required=True, help="TMDB API key")
    parser.add_argument("--source-db", default=str(DEFAULT_SOURCE_DB), help="Path to movies.db")
    parser.add_argument("--db", default=str(DEFAULT_FLUD_DB), help="Path to flud.db")
    args = parser.parse_args()

    run(
        provider_id=args.provider,
        api_key=args.tmdb_key,
        source_db=Path(args.source_db),
        flud_db=Path(args.db),
    )
