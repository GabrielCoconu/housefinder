#!/usr/bin/env python3
"""
Interactive setup for Imobiliare.ro browser state.

Opens imobiliare.ro in Safari (your real browser, not Playwright).
After you solve the CAPTCHA, the script reads cookies from Safari
and saves them as a Playwright-compatible state file.

Requires: Safari > Develop > Allow JavaScript from Apple Events

Usage:
    python setup_imobiliare.py
"""

import json
import subprocess
import sys
import time

from imobiliare_auth import get_state_path


IMOBILIARE_URL = 'https://www.imobiliare.ro/vanzare-case-vile/bucuresti'


def get_safari_cookies() -> str | None:
    """Extract document.cookie from the current Safari tab via AppleScript."""
    script = (
        'tell application "Safari" to do JavaScript "document.cookie" '
        'in current tab of first window'
    )
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_safari_url() -> str | None:
    """Get the URL of the current Safari tab."""
    script = 'tell application "Safari" to get URL of current tab of first window'
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def parse_cookie_string(cookie_str: str, domain: str = '.imobiliare.ro') -> list[dict]:
    """Parse a document.cookie string into Playwright storage_state format."""
    cookies = []
    if not cookie_str:
        return cookies
    for pair in cookie_str.split('; '):
        if '=' not in pair:
            continue
        name, _, value = pair.partition('=')
        cookies.append({
            'name': name.strip(),
            'value': value.strip(),
            'domain': domain,
            'path': '/',
            'expires': time.time() + 86400,  # 24h from now
            'httpOnly': False,
            'secure': True,
            'sameSite': 'None',
        })
    return cookies


def main():
    print("=" * 60)
    print("  Imobiliare.ro — Browser State Setup (Safari)")
    print("=" * 60)
    print()
    print("This script will:")
    print("  1. Open imobiliare.ro in Safari")
    print("  2. You solve the CAPTCHA in Safari")
    print("  3. Press ENTER here to extract cookies")
    print()
    print("Pre-requisite: Enable Safari > Develop > Allow JavaScript")
    print("               from Apple Events (one-time setting)")
    print()

    # Open in Safari
    subprocess.run(['open', '-a', 'Safari', IMOBILIARE_URL])

    input("✅  Solve the CAPTCHA in Safari, then press ENTER here...")

    # Verify we're on imobiliare.ro
    url = get_safari_url()
    if url and 'imobiliare.ro' not in url:
        print(f"⚠️  Safari is on {url}, not imobiliare.ro")
        print("   Navigate to imobiliare.ro in Safari and try again.")
        sys.exit(1)

    # Extract cookies
    cookie_str = get_safari_cookies()
    if cookie_str is None:
        print()
        print("❌  Could not read Safari cookies.")
        print("   Enable: Safari > Develop > Allow JavaScript from Apple Events")
        print()
        print("   If the Develop menu is not visible:")
        print("   Safari > Settings > Advanced > Show features for web developers")
        sys.exit(1)

    if not cookie_str:
        print("⚠️  Safari returned empty cookies. Make sure the page loaded.")
        sys.exit(1)

    cookies = parse_cookie_string(cookie_str)

    # Build Playwright storage_state
    state = {'cookies': cookies, 'origins': []}
    state_path = get_state_path()
    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)

    # Report
    print(f"\n💾  Saved {len(cookies)} cookies to {state_path}")
    dd = [c for c in cookies if 'datadome' in c['name'].lower()]
    if dd:
        print("✅  DataDome cookie found!")
    else:
        print("⚠️  No DataDome cookie — protection bypass may not work")

    print("\n🎉  Done! You can now run scout_agent.py.")


if __name__ == '__main__':
    main()
