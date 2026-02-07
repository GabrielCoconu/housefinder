#!/usr/bin/env python3
"""
Casa Hunt - Imobiliare.ro Scraper
Scrapes house listings from Imobiliare.ro
"""

import logging
import random
import re
import time
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper_utils import Listing, extract_price, extract_surface, extract_rooms


logger = logging.getLogger(__name__)

# Base URL for Imobiliare.ro
BASE_URL = "https://www.imobiliare.ro"

# Request headers to mimic browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ro;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def scrape_imobiliare(max_pages: int = 3, max_price: int = 200000) -> List[Listing]:
    """
    Scrape house listings from Imobiliare.ro.
    
    Args:
        max_pages: Maximum number of pages to scrape
        max_price: Maximum price filter in EUR
        
    Returns:
        List of Listing objects
    """
    logger.info(f"Starting Imobiliare scraper (max {max_pages} pages)")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    listings = []
    
    # Search for houses/villas in Bucharest
    # Price max is set to 990000 RON (~200k EUR)
    search_url = f"{BASE_URL}/vanzare-case-vile/bucuresti"
    
    for page_num in range(1, max_pages + 1):
        url = f"{search_url}?pret-max=990000&pagina={page_num}"
        logger.info(f"  Fetching page {page_num}: {url}")
        
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            page_listings = parse_listings_page(soup)
            
            logger.info(f"  Found {len(page_listings)} listings on page {page_num}")
            listings.extend(page_listings)
            
            # Stop if no listings found
            if not page_listings:
                logger.info("  No more listings found, stopping")
                break
            
            # Random delay between requests
            time.sleep(random.uniform(1, 3))
            
        except requests.RequestException as e:
            logger.error(f"  Request error on page {page_num}: {e}")
            break
        except Exception as e:
            logger.error(f"  Error processing page {page_num}: {e}")
            continue
    
    logger.info(f"Imobiliare scraper complete: {len(listings)} total listings")
    return listings


def parse_listings_page(soup: BeautifulSoup) -> List[Listing]:
    """
    Parse a listings page and extract individual listings.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        List of Listing objects
    """
    listings = []
    
    # Try multiple possible selectors for listing cards
    selectors = [
        'div.box-anunt',
        'div.anunt',
        '[data-testid="listing-card"]',
        'article.property',
        '.listing-item'
    ]
    
    cards = []
    for selector in selectors:
        cards = soup.select(selector)
        if cards:
            logger.debug(f"  Found cards with selector: {selector}")
            break
    
    for card in cards:
        try:
            listing = parse_listing_card(card)
            if listing:
                listings.append(listing)
        except Exception as e:
            logger.debug(f"  Error parsing card: {e}")
            continue
    
    return listings


def parse_listing_card(card) -> Optional[Listing]:
    """
    Parse a single listing card.
    
    Args:
        card: BeautifulSoup element representing a listing card
        
    Returns:
        Listing object or None if invalid
    """
    # Extract URL
    link_elem = card.find('a', href=re.compile(r'/vanzare'))
    if not link_elem:
        return None
    
    href = link_elem.get('href', '')
    if not href:
        return None
    
    # Ensure absolute URL
    url = urljoin(BASE_URL, href) if not href.startswith('http') else href
    
    # Extract title
    title_elem = card.find(['h2', 'h3', '.titlu', '.title'])
    title = title_elem.get_text(strip=True) if title_elem else 'N/A'
    
    # Extract price
    price_elem = card.find(['.pret', '.price', '[class*="pret"]'])
    price_raw = price_elem.get_text(strip=True) if price_elem else ''
    price_eur = extract_price(price_raw)
    
    # Extract location
    location_elem = card.find(['.locatie', '.location', '[class*="locatie"]'])
    location = location_elem.get_text(strip=True) if location_elem else ''
    
    # Extract features
    features_elem = card.find(['.caracteristici', '.features'])
    features_text = features_elem.get_text(strip=True) if features_elem else ''
    
    # Extract surface and rooms from features
    surface_mp = extract_surface(features_text)
    rooms = extract_rooms(features_text)
    
    # Extract description
    desc_elem = card.find(['.descriere', '.description'])
    description = desc_elem.get_text(strip=True)[:500] if desc_elem else ''
    
    # Create listing
    listing = Listing(
        url=url,
        title=title,
        source='imobiliare.ro',
        price_eur=price_eur,
        price_raw=price_raw,
        location=location,
        surface_mp=surface_mp,
        rooms=rooms,
        description=description,
        features_raw=features_text
    )
    
    return listing


def scrape_imobiliare_with_playwright(max_pages: int = 3) -> List[Listing]:
    """
    Alternative scraper using Playwright for JavaScript-rendered pages.
    Falls back to this if requests-based scraper fails.
    
    Args:
        max_pages: Maximum number of pages to scrape
        
    Returns:
        List of Listing objects
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed, skipping JS-rendered scraper")
        return []
    
    listings = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS['User-Agent'])
        page = context.new_page()
        
        for page_num in range(1, max_pages + 1):
            url = f"{BASE_URL}/vanzare-case-vile/bucuresti?pret-max=990000&pagina={page_num}"
            logger.info(f"  [Playwright] Fetching page {page_num}")
            
            try:
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.wait_for_timeout(3000)  # Wait for JS to load
                
                # Accept cookies if present
                try:
                    cookie_btn = page.query_selector('button:has-text("Accept"), button:has-text("Acord"), #cookieAccept')
                    if cookie_btn:
                        cookie_btn.click()
                        page.wait_for_timeout(1000)
                except:
                    pass
                
                # Extract data using page.evaluate
                page_listings = page.evaluate('''() => {
                    const listings = [];
                    const cards = document.querySelectorAll('.box-anunt, .anunt, [data-testid="listing-card"]');
                    
                    cards.forEach(card => {
                        const data = {};
                        
                        const link = card.querySelector('a[href*="/vanzare"]');
                        if (link) {
                            data.url = link.href;
                            data.title = link.textContent.trim();
                        }
                        
                        const price = card.querySelector('.pret, .price, [class*="pret"]');
                        if (price) {
                            data.price_raw = price.textContent.trim();
                        }
                        
                        const loc = card.querySelector('.locatie, .location, [class*="locatie"]');
                        if (loc) {
                            data.location = loc.textContent.trim();
                        }
                        
                        const features = card.querySelector('.caracteristici, .features');
                        if (features) {
                            data.features = features.textContent.trim();
                        }
                        
                        listings.push(data);
                    });
                    
                    return listings;
                }''')
                
                for item in page_listings:
                    if not item.get('url'):
                        continue
                    
                    listing = Listing(
                        url=item['url'],
                        title=item.get('title', 'N/A')[:200],
                        source='imobiliare.ro',
                        price_raw=item.get('price_raw', ''),
                        price_eur=extract_price(item.get('price_raw')),
                        location=item.get('location', ''),
                        surface_mp=extract_surface(item.get('features', '')),
                        features_raw=item.get('features', '')
                    )
                    
                    listings.append(listing)
                
                logger.info(f"  [Playwright] Found {len(page_listings)} listings")
                
                if not page_listings:
                    break
                    
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"  [Playwright] Error on page {page_num}: {e}")
                break
        
        browser.close()
    
    return listings


if __name__ == '__main__':
    # Test the scraper
    from scraper_utils import setup_logging
    setup_logging(level=logging.DEBUG)
    
    results = scrape_imobiliare(max_pages=1)
    print(f"\nFound {len(results)} listings:")
    for r in results[:5]:
        print(f"  - {r.title[:60]}... ({r.price_raw or 'N/A'})")
