"""
Imobiliare.ro authentication state utilities.

Manages the browser state file (cookies, localStorage) used to bypass
DataDome anti-bot protection on imobiliare.ro.
"""

import os
import json
import time

# State file lives next to this module
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'imobiliare_state.json')

# Consistent user-agent across setup and scraping scripts.
# DataDome fingerprints include UA; mismatch triggers re-challenge.
USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)


def get_state_path() -> str:
    """Return absolute path to the browser state JSON file."""
    return STATE_FILE


def state_file_exists() -> bool:
    """Check whether the saved browser state file exists."""
    return os.path.isfile(STATE_FILE)


def needs_refresh(max_age_hours: float = 12) -> bool:
    """Return True if the state file is missing or older than *max_age_hours*."""
    if not state_file_exists():
        return True
    age_seconds = time.time() - os.path.getmtime(STATE_FILE)
    return age_seconds > max_age_hours * 3600


def is_blocked(page_content: str) -> bool:
    """Detect a DataDome block page in raw HTML content."""
    markers = [
        'Accesul este restricționat temporar',
        'geo.captcha-delivery.com',
        'dd.datadome.co',
        'DataDome',
        'captcha-delivery.com',
    ]
    return any(m in page_content for m in markers)
