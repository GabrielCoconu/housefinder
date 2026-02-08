"""
Local URL cache to avoid redundant Supabase API calls.

Stores known URLs in a JSON file. On each run:
  1. Load cache from disk
  2. Filter out already-cached URLs (skip Supabase check)
  3. For remaining URLs, check Supabase (fallback)
  4. Update cache with all known URLs (existing + newly inserted)
"""

import json
import os
import logging
from typing import Set, List

logger = logging.getLogger('url_cache')

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'url_cache.json')


def load_cache() -> Set[str]:
    """Load cached URLs from disk. Returns empty set if file missing/corrupt."""
    try:
        if os.path.isfile(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
            urls = set(data.get('urls', []))
            logger.info(f"Loaded {len(urls)} URLs from local cache")
            return urls
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Cache load failed, starting fresh: {e}")
    return set()


def save_cache(urls: Set[str]) -> None:
    """Persist URL set to disk atomically."""
    tmp_path = CACHE_FILE + '.tmp'
    try:
        with open(tmp_path, 'w') as f:
            json.dump({'urls': sorted(urls)}, f)
        os.replace(tmp_path, CACHE_FILE)
        logger.info(f"Saved {len(urls)} URLs to local cache")
    except IOError as e:
        logger.error(f"Cache save failed: {e}")


def filter_new_urls(all_urls: List[str], db) -> Set[str]:
    """
    Given a list of URLs and a SupabaseManager, return set of known/existing URLs.

    - URLs found in local cache are immediately known as duplicates
    - Remaining URLs are checked against Supabase (fallback)
    """
    cache = load_cache()

    cached = {u for u in all_urls if u in cache}
    unknown = [u for u in all_urls if u not in cache]

    logger.info(f"Cache hit: {len(cached)}/{len(all_urls)} URLs already known locally")

    if unknown:
        logger.info(f"Checking {len(unknown)} unknown URLs against Supabase...")
        supabase_existing = db.get_existing_urls(unknown)
        cached.update(supabase_existing)

    return cached
