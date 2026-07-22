#!/usr/bin/env python3
import csv
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
import requests
from lxml import etree

SITEMAP_URL = "https://fmoviess.org/sitemap.xml"
IMAGE_BASE_URL = "https://img.cdno.my.id/thumb/w_200/h_300/"
DB_FILE = "movies.db"
CSV_FILE = "movies.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

def fetch_xml(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return etree.fromstring(response.content)
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def extract_slug(page_url):
    cleaned_url = page_url.rstrip("/")
    slug = cleaned_url.split("/")[-1]
    return slug

def detect_media_type(slug):
    # Check if slug contains season or episode indicators
    if re.search(r"-(season|episode)-\d+", slug, re.IGNORECASE) or "-season-" in slug.lower():
        return "tv_show"
    return "movie"

def parse_sitemap():
    root = fetch_xml(SITEMAP_URL)
    if root is None:
        print("Failed to load root sitemap.", file=sys.stderr)
        sys.exit(1)

    sitemaps = [loc.text for loc in root.findall(".//s:sitemap/s:loc", NS) if loc.text]
    
    page_urls = []
    
    if sitemaps:
        print(f"Found {len(sitemaps)} sub-sitemaps. Fetching concurrently...")
        def process_sub_sitemap(url):
            xml_tree = fetch_xml(url)
            if xml_tree is not None:
                return [loc.text for loc in xml_tree.findall(".//s:url/s:loc", NS) if loc.text]
            return []

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(process_sub_sitemap, sitemaps)
            for urls in results:
                page_urls.extend(urls)
    else:
        page_urls = [loc.text for loc in root.findall(".//s:url/s:loc", NS) if loc.text]

    print(f"Extracted {len(page_urls)} total page URLs from sitemap.")

    records = []
    seen = set()
    for page_url in page_urls:
        if page_url in seen:
            continue
        seen.add(page_url)
        
        slug = extract_slug(page_url)
        if not slug or page_url.rstrip("/") == "https://fmoviess.org":
            continue
            
        image_path = f"{IMAGE_BASE_URL}{slug}.jpg"
        media_type = detect_media_type(slug)
        records.append((page_url, image_path, media_type))

    # Populate SQLite DB
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS movies")
    cursor.execute("""
        CREATE TABLE movies (
            page_url TEXT PRIMARY KEY,
            image_path TEXT,
            media_type TEXT
        )
    """)
    cursor.executemany("INSERT INTO movies (page_url, image_path, media_type) VALUES (?, ?, ?)", records)
    
    # Create convenience views for filtering
    cursor.execute("DROP VIEW IF EXISTS movies_only")
    cursor.execute("CREATE VIEW movies_only AS SELECT page_url, image_path FROM movies WHERE media_type = 'movie'")
    
    cursor.execute("DROP VIEW IF EXISTS tv_shows_only")
    cursor.execute("CREATE VIEW tv_shows_only AS SELECT page_url, image_path FROM movies WHERE media_type = 'tv_show'")

    conn.commit()
    conn.close()

    # Populate CSV
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["page_url", "image_path", "media_type"])
        writer.writerows(records)

    movie_count = sum(1 for r in records if r[2] == 'movie')
    tv_count = sum(1 for r in records if r[2] == 'tv_show')

    print(f"Successfully ingested {len(records)} records ({movie_count} movies, {tv_count} TV show seasons) into {DB_FILE} and {CSV_FILE}.")
    return len(records)

if __name__ == "__main__":
    parse_sitemap()
