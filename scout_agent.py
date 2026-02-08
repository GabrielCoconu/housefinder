#!/usr/bin/env python3
"""
Casa Hunt - Scout Agent
Scrapes Imobiliare.ro and Storia.ro, saves to Supabase
"""

import os
import sys

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import re
import json
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from supabase_manager import SupabaseManager
from imobiliare_auth import (
    state_file_exists, get_state_path, needs_refresh, is_blocked, USER_AGENT
)

# Setup logging to file
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'scout.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('scout_agent')


@dataclass
class ScrapingConfig:
    """Configuration for scraping."""
    max_pages: int = 50  # Bulk scraping: up to 50 pages
    max_price: int = 200000
    min_price: int = 100000
    location: str = "bucuresti"
    listing_type: str = "case-vile"  # houses/villas
    batch_size: int = 100  # Process in batches of 100
    max_listings_total: int = 1000  # Stop after 1000 listings per source
    rate_limit_delay: float = 1.0  # Seconds between requests


@dataclass  
class Listing:
    """Represents a property listing."""
    source: str
    external_id: str
    url: str
    title: str
    price_raw: str
    price_eur: Optional[int]
    location: str
    surface_mp: Optional[int]
    rooms: Optional[int]
    features_raw: str
    metro_nearby: bool
    scraped_at: str
    raw_data: Dict


class ScoutAgent:
    """Scrapes real estate listings from multiple sources."""
    
    def __init__(self):
        self.db = SupabaseManager()
        self.config = ScrapingConfig()
        self.listings: List[Listing] = []
        
        # Price conversion rate (RON to EUR)
        self.eur_rate = 4.97
    
    def parse_price(self, price_text: str) -> Tuple[str, Optional[int]]:
        """Parse price text to raw and EUR values.

        Handles European formatting where dots are thousand separators
        and commas are decimal separators (e.g. "875.000 €", "1.620.000 €").
        """
        if not price_text:
            return "", None

        # Strip whitespace/newlines that come from HTML
        price_text_clean = ' '.join(price_text.split())

        # Extract digits, dots and commas
        price_clean = re.sub(r'[^\d.,]', '', price_text_clean)

        # Handle European format: dots are thousand separators, commas are decimal
        # e.g. "875.000" -> "875000", "1.620.000" -> "1620000", "224,25" -> "224.25"
        if '.' in price_clean and ',' in price_clean:
            # Both present: dots are thousands, comma is decimal (e.g. "1.234,56")
            price_clean = price_clean.replace('.', '').replace(',', '.')
        elif '.' in price_clean:
            # Only dots: check if it looks like thousands separator
            # "875.000" has exactly 3 digits after dot = thousand separator
            parts = price_clean.split('.')
            if all(len(p) == 3 for p in parts[1:]):
                price_clean = price_clean.replace('.', '')
            # else: single dot like "875.5" is a decimal
        elif ',' in price_clean:
            # Only comma: it's a decimal separator
            price_clean = price_clean.replace(',', '.')

        try:
            price_value = float(price_clean)
            if 'ron' in price_text.lower() or 'lei' in price_text.lower():
                price_eur = int(price_value / self.eur_rate)
            else:
                price_eur = int(price_value)

            return price_text_clean, price_eur
        except (ValueError, TypeError):
            return price_text_clean, None
    
    def parse_surface(self, surface_text: str) -> Optional[int]:
        """Extract surface area in mp."""
        if not surface_text:
            return None
        
        match = re.search(r'(\d+)\s*mp', surface_text.lower())
        if match:
            return int(match.group(1))
        
        # Try just numbers
        match = re.search(r'(\d+)', surface_text)
        if match:
            return int(match.group(1))
        
        return None
    
    def parse_rooms(self, rooms_text: str) -> Optional[int]:
        """Extract number of rooms."""
        if not rooms_text:
            return None
        
        match = re.search(r'(\d+)\s*(?:camere|camera)', rooms_text.lower())
        if match:
            return int(match.group(1))
        
        # Just numbers
        match = re.search(r'(\d+)', rooms_text)
        if match:
            return int(match.group(1))
        
        return None
    
    def check_metro_nearby(self, text: str) -> bool:
        """Check if listing mentions metro proximity."""
        metro_keywords = [
            'metrou', 'statie', 'pipera', 'universitate', 'romana',
            'victoriei', 'pallady', 'berceni', 'dimitrie', 'leonida',
            'titan', 'obor', 'muncii', 'timpuri noi', 'lujerului',
            'politehnica', 'eroilor', 'unirii', 'aviatorilor'
        ]
        
        text_lower = text.lower()
        return any(kw in text_lower for kw in metro_keywords)
    
    def validate_listing(self, listing) -> tuple[bool, str]:
        """Validate listing before saving. Returns (is_valid, error_message)."""
        # Handle both Dict and Listing objects
        if isinstance(listing, dict):
            url = listing.get('url', '')
            price = listing.get('price_eur')
            location = listing.get('location', '')
            title = listing.get('title', '')
        else:
            # It's a Listing dataclass
            url = listing.url
            price = listing.price_eur
            location = listing.location
            title = listing.title
        
        # Validate URL
        if not url:
            return False, "URL is empty"
        
        # Reject test URLs
        test_domains = ['test.com', 'example.com', 'localhost']
        if any(td in url for td in test_domains):
            return False, f"Test URL rejected: {url}"
        
        # Must be from allowed sources
        allowed_sources = ['imobiliare.ro', 'storia.ro']
        if not any(src in url for src in allowed_sources):
            return False, f"URL not from allowed source: {url}"
        
        # Validate price
        if price is None:
            return False, "Price is None"
        
        if price < 10000:
            return False, f"Price too low: {price}€"
        
        if price > 1000000:
            return False, f"Price too high: {price}€"
        
        # Validate location
        if not location or location in ['', 'N/A']:
            return False, "Location is empty"
        
        # Check if title mentions a non-Bucharest city (reject listings outside Bucharest)
        non_bucharest_cities = ['liebling', 'techirghiol', 'chinteni', 'floresti', 'cluj', 'timisoara', 
                                'iasi', 'constanta', 'brasov', 'craiova', 'oradea', 'arad', 'sibiu',
                                'galati', 'ploiesti', 'braila', 'buzau', 'focsani', 'bacau', 'suceava',
                                'secusigiu', 'hoghiz', 'cuciulata', 'slatioara', 'suCEAGU', 'lerești',
                                'paleu', 'seuca', 'rapsig', 'maramures', 'giurgiu', 'ialomita']
        title_lower = title.lower()
        for city in non_bucharest_cities:
            if city in title_lower:
                return False, f"Listing outside Bucharest: {city}"
        
        # For Storia/Imobiliare, "Bucuresti" is acceptable — the search is already
        # filtered to Bucharest, so all results are in the city.  We only reject
        # listings that explicitly mention a non-Bucharest city (handled above).
        # No need to require neighborhood in the title.
        
        return True, "OK"
    
    async def scrape_imobiliare(self, page: Page) -> List[Listing]:
        """Scrape Imobiliare.ro listings."""
        logger.info("🕵️  Scraping Imobiliare.ro...")
        listings = []
        
        try:
            # Build search URL
            base_url = "https://www.imobiliare.ro"
            search_url = f"{base_url}/vanzare-case-vile/{self.config.location}?pretmax={self.config.max_price}"
            
            logger.info(f"Navigating to: {search_url}")
            await page.goto(search_url, wait_until='networkidle', timeout=30000)
            
            # Accept cookies if present
            try:
                cookie_btn = await page.query_selector('button[data-testid="cookie-accept"]')
                if cookie_btn:
                    await cookie_btn.click()
                    await asyncio.sleep(1)
            except:
                pass
            
            # Wait for listings to load
            await page.wait_for_selector('.box-anunt', timeout=10000)
            
            # Get all listing cards
            cards = await page.query_selector_all('.box-anunt')
            logger.info(f"Found {len(cards)} listings on Imobiliare")
            
            for card in cards[:10]:  # Limit to first 10 for testing
                try:
                    # Extract data
                    title_el = await card.query_selector('.titlu-anunt, h2')
                    title = await title_el.inner_text() if title_el else "N/A"
                    
                    price_el = await card.query_selector('.pret, .price')
                    price_text = await price_el.inner_text() if price_el else ""
                    price_raw, price_eur = self.parse_price(price_text)
                    
                    location_el = await card.query_selector('.location, .locatie')
                    location = await location_el.inner_text() if location_el else "Bucuresti"
                    
                    surface_el = await card.query_selector('.surface, .suprafata')
                    surface_text = await surface_el.inner_text() if surface_el else ""
                    surface_mp = self.parse_surface(surface_text)
                    
                    rooms_el = await card.query_selector('.rooms, .camere')
                    rooms_text = await rooms_el.inner_text() if rooms_el else ""
                    rooms = self.parse_rooms(rooms_text)
                    
                    link_el = await card.query_selector('a')
                    href = await link_el.get_attribute('href') if link_el else ""
                    url = urljoin(base_url, href)
                    
                    features = f"{surface_text} {rooms_text}".strip()
                    metro_nearby = self.check_metro_nearby(f"{title} {location} {features}")
                    
                    listing = Listing(
                        source='imobiliare.ro',
                        external_id=href.split('/')[-1] if '/' in href else '',
                        url=url,
                        title=title.strip(),
                        price_raw=price_raw,
                        price_eur=price_eur,
                        location=location.strip(),
                        surface_mp=surface_mp,
                        rooms=rooms,
                        features_raw=features,
                        metro_nearby=metro_nearby,
                        scraped_at=datetime.now(timezone.utc).isoformat(),
                        raw_data={'selector': 'box-anunt'}
                    )
                    
                    # Validate before adding
                    is_valid, error_msg = self.validate_listing(listing)
                    if is_valid:
                        listings.append(listing)
                    else:
                        logger.warning(f"❌ Rejected listing: {error_msg} - {title[:30]}")
                    
                except Exception as e:
                    logger.warning(f"Error parsing Imobiliare card: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error scraping Imobiliare: {e}")
        
        logger.info(f"✅ Scraped {len(listings)} listings from Imobiliare.ro")
        return listings
    
    async def scrape_storia(self, page: Page) -> List[Listing]:
        """Scrape Storia.ro listings."""
        logger.info("🕵️  Scraping Storia.ro...")
        listings = []
        
        try:
            base_url = "https://www.storia.ro"
            search_url = f"{base_url}/ro/cautare/vanzare/casa/vila/bucuresti?priceMax={self.config.max_price}"
            
            logger.info(f"Navigating to: {search_url}")
            await page.goto(search_url, wait_until='networkidle', timeout=30000)
            
            # Accept cookies
            try:
                cookie_btn = await page.query_selector('button[id="onetrust-accept-btn-handler"]')
                if cookie_btn:
                    await cookie_btn.click()
                    await asyncio.sleep(1)
            except:
                pass
            
            # Wait for listings
            await page.wait_for_selector('[data-cy="listing-item"]', timeout=10000)
            
            cards = await page.query_selector_all('[data-cy="listing-item"]')
            logger.info(f"Found {len(cards)} listings on Storia")
            
            for card in cards[:10]:  # Limit to first 10 for testing
                try:
                    title_el = await card.query_selector('h3, [data-cy="listing-item-title"]')
                    title = await title_el.inner_text() if title_el else "N/A"
                    
                    price_el = await card.query_selector('[data-cy="listing-item-price"]')
                    price_text = await price_el.inner_text() if price_el else ""
                    price_raw, price_eur = self.parse_price(price_text)
                    
                    location_el = await card.query_selector('[data-cy="listing-item-location"]')
                    location = await location_el.inner_text() if location_el else "Bucuresti"
                    
                    # Storia often has features in subtitle
                    subtitle_el = await card.query_selector('[data-cy="listing-item-subtitle"]')
                    subtitle = await subtitle_el.inner_text() if subtitle_el else ""
                    
                    surface_mp = self.parse_surface(subtitle)
                    rooms = self.parse_rooms(subtitle)
                    
                    link_el = await card.query_selector('a')
                    href = await link_el.get_attribute('href') if link_el else ""
                    url = urljoin(base_url, href)
                    
                    features = subtitle.strip()
                    metro_nearby = self.check_metro_nearby(f"{title} {location} {features}")
                    
                    listing = Listing(
                        source='storia.ro',
                        external_id=href.split('/')[-1] if '/' in href else '',
                        url=url,
                        title=title.strip(),
                        price_raw=price_raw,
                        price_eur=price_eur,
                        location=location.strip(),
                        surface_mp=surface_mp,
                        rooms=rooms,
                        features_raw=features,
                        metro_nearby=metro_nearby,
                        scraped_at=datetime.now(timezone.utc).isoformat(),
                        raw_data={'selector': 'listing-item'}
                    )
                    listings.append(listing)
                    
                except Exception as e:
                    logger.warning(f"Error parsing Storia card: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error scraping Storia: {e}")
        
        logger.info(f"✅ Scraped {len(listings)} listings from Storia.ro")
        return listings
    
    async def scrape_imobiliare_bulk(self) -> List[Listing]:
        """Bulk scrape Imobiliare.ro with pagination using curl_cffi + saved cookies."""
        from bs4 import BeautifulSoup
        from curl_cffi.requests import AsyncSession

        logger.info(f"🕵️  Bulk scraping Imobiliare.ro (max {self.config.max_pages} pages)...")
        all_listings = []
        base_url = "https://www.imobiliare.ro"

        # Load cookies from state file
        with open(get_state_path()) as f:
            state = json.load(f)
        cookies = {c['name']: c['value'] for c in state.get('cookies', [])}

        async with AsyncSession(impersonate="safari17_0") as client:
            for page_num in range(1, self.config.max_pages + 1):
                if len(all_listings) >= self.config.max_listings_total:
                    logger.info(f"⛔ Reached max listings limit: {self.config.max_listings_total}")
                    break

                try:
                    if page_num == 1:
                        search_url = f"{base_url}/vanzare-case-vile/{self.config.location}?pretmax={self.config.max_price}"
                    else:
                        search_url = f"{base_url}/vanzare-case-vile/{self.config.location}?pagina={page_num}&pretmax={self.config.max_price}"

                    logger.info(f"  📄 Page {page_num}: {search_url}")
                    response = await client.get(
                        search_url,
                        cookies=cookies,
                        headers={
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'ro-RO,ro;q=0.9,en;q=0.5',
                        },
                        allow_redirects=True,
                        timeout=30,
                    )
                    if response.status_code == 403:
                        logger.error(f"  🚫 403 Forbidden on page {page_num} — re-run setup_imobiliare.py.")
                        break
                    response.raise_for_status()
                    html = response.text

                    if is_blocked(html):
                        logger.error(f"  🚫 DataDome block on page {page_num} — re-run setup_imobiliare.py.")
                        break

                    soup = BeautifulSoup(html, 'html.parser')
                    cards = soup.select('.listing-card')
                    logger.info(f"  📊 Found {len(cards)} listings on page {page_num}")

                    if not cards:
                        logger.info("  ✅ No more listings available")
                        break

                    for card in cards:
                        try:
                            # Title: prefer the hidden desktop title, fall back to line-clamp
                            title_el = card.select_one('span.text-title') or card.select_one('span.line-clamp-2')
                            title = title_el.get_text(strip=True) if title_el else "N/A"

                            # Price: bold text with € sign
                            price_el = card.select_one('p.text-title')
                            price_text = price_el.get_text(strip=True) if price_el else ""
                            price_raw, price_eur = self.parse_price(price_text)

                            # Location: grey text below the title
                            location_el = card.select_one('div.text-grey-650 p, div.text-grey-650')
                            location = location_el.get_text(strip=True) if location_el else "Bucuresti"

                            # Features come as swiper-slide chips
                            feature_chips = card.select('.swiper-slide span.whitespace-nowrap')
                            feature_texts = [chip.get_text(strip=True) for chip in feature_chips]

                            surface_text = next((f for f in feature_texts if 'mp' in f and 'teren' not in f), "")
                            surface_mp = self.parse_surface(surface_text)

                            rooms_text = next((f for f in feature_texts if 'camer' in f), "")
                            rooms = self.parse_rooms(rooms_text)

                            link_el = card.select_one('a[href*="/oferta/"]')
                            href = link_el['href'] if link_el else ""
                            url = urljoin(base_url, href)

                            features = " ".join(feature_texts)
                            metro_nearby = self.check_metro_nearby(f"{title} {location} {features}")

                            listing = Listing(
                                source='imobiliare.ro',
                                external_id=href.split('/')[-1] if '/' in href else '',
                                url=url,
                                title=title.strip(),
                                price_raw=price_raw,
                                price_eur=price_eur,
                                location=location.strip(),
                                surface_mp=surface_mp,
                                rooms=rooms,
                                features_raw=features,
                                metro_nearby=metro_nearby,
                                scraped_at=datetime.now(timezone.utc).isoformat(),
                                raw_data={'page': page_num}
                            )

                            is_valid, error_msg = self.validate_listing(listing)
                            if is_valid:
                                all_listings.append(listing)
                            else:
                                logger.debug(f"  ❌ Rejected: {error_msg}")

                        except Exception as e:
                            logger.warning(f"  ⚠️  Error parsing card: {e}")
                            continue

                    logger.info(f"  ✅ Page {page_num} complete. Total: {len(all_listings)} listings")

                    if page_num < self.config.max_pages:
                        await asyncio.sleep(self.config.rate_limit_delay)

                except Exception as e:
                    logger.error(f"  ❌ Error on page {page_num}: {e}")
                    continue

        logger.info(f"✅ Imobiliare.ro bulk complete: {len(all_listings)} listings")
        return all_listings
    
    def extract_next_data(self, html: str) -> Optional[Dict]:
        """Extract JSON data from __NEXT_DATA__ script tag."""
        try:
            # Find the __NEXT_DATA__ script tag
            pattern = r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'
            match = re.search(pattern, html, re.DOTALL)
            
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
            
            return None
        except Exception as e:
            logger.error(f"Error extracting NEXT_DATA: {e}")
            return None

    async def scrape_storia_json(self, page_num: int = 1) -> List[Listing]:
        """Scrape Storia.ro using __NEXT_DATA__ JSON extraction (fast, no browser needed)."""
        logger.info(f"🕵️  Scraping Storia.ro page {page_num} via JSON...")
        listings = []
        base_url = "https://www.storia.ro"
        
        try:
            # Build URL with pagination - use proper Storia URL format
            # Note: Storia redirects generic searches to "toata-romania", need specific location ID
            if page_num == 1:
                search_url = f"{base_url}/ro/rezultate/vanzare/casa/bucuresti?priceMax={self.config.max_price}"
            else:
                search_url = f"{base_url}/ro/rezultate/vanzare/casa/bucuresti?page={page_num}&priceMax={self.config.max_price}"
            
            logger.info(f"  📄 Fetching: {search_url}")
            
            # Use httpx for fast HTTP request
            async with httpx.AsyncClient(
                headers={
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                },
                follow_redirects=True,
                timeout=30.0
            ) as client:
                response = await client.get(search_url)
                response.raise_for_status()
                html = response.text
                
                logger.info(f"  📊 HTML size: {len(html):,} bytes")
                
                # Extract NEXT_DATA JSON
                next_data = self.extract_next_data(html)
                
                if not next_data:
                    logger.warning("  ⚠️  Could not extract __NEXT_DATA__")
                    return listings
                
                # Navigate to search results
                try:
                    search_ads = next_data['props']['pageProps']['data']['searchAds']['items']
                    logger.info(f"  📊 Found {len(search_ads)} listings in JSON")
                except (KeyError, TypeError) as e:
                    logger.error(f"  ❌ JSON structure error: {e}")
                    return listings
                
                # Parse each listing
                for item in search_ads:
                    try:
                        listing_id = str(item.get('id', ''))
                        slug = item.get('slug', '')
                        title = item.get('title', 'N/A')
                        
                        # Build URL
                        url = f"{base_url}/ro/anunt/{slug}-{listing_id}"
                        
                        # Price
                        total_price = item.get('totalPrice', {})
                        price_value = total_price.get('value')
                        price_currency = total_price.get('currency', 'EUR')
                        
                        if price_value:
                            if price_currency == 'RON':
                                price_eur = int(price_value / self.eur_rate)
                            else:
                                price_eur = int(price_value)
                            price_raw = f"{price_value} {price_currency}"
                        else:
                            price_eur = None
                            price_raw = ""
                        
                        # Location
                        location_data = item.get('location', {})
                        city = location_data.get('city', {}).get('name', '')
                        province = location_data.get('province', {}).get('name', '')
                        location = f"{city}, {province}" if city and province else city or province or "Bucuresti"
                        
                        # Features
                        surface_mp_raw = item.get('areaInSquareMeters')
                        surface_mp = int(surface_mp_raw) if surface_mp_raw is not None else None
                        rooms_raw = item.get('roomsNumber')
                        # Convert string rooms (ONE, TWO, THREE, FOUR) to integers
                        rooms_map = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5, 
                                     'SIX': 6, 'SEVEN': 7, 'EIGHT': 8, 'NINE': 9, 'TEN': 10}
                        if isinstance(rooms_raw, str):
                            rooms = rooms_map.get(rooms_raw.upper())
                        else:
                            rooms = int(rooms_raw) if rooms_raw is not None else None
                        terrain = item.get('terrainAreaInSquareMeters')
                        
                        # Features raw
                        features_parts = []
                        if surface_mp:
                            features_parts.append(f"{surface_mp} mp")
                        if terrain:
                            features_parts.append(f"teren {terrain} mp")
                        if rooms:
                            features_parts.append(f"{rooms} camere")
                        features_raw = " | ".join(features_parts)
                        
                        # Metro check
                        short_desc = item.get('shortDescription', '')
                        metro_nearby = self.check_metro_nearby(f"{title} {location} {short_desc}")
                        
                        listing = Listing(
                            source='storia.ro',
                            external_id=listing_id,
                            url=url,
                            title=title.strip(),
                            price_raw=price_raw,
                            price_eur=price_eur,
                            location=location.strip(),
                            surface_mp=surface_mp,
                            rooms=rooms,
                            features_raw=features_raw,
                            metro_nearby=metro_nearby,
                            scraped_at=datetime.now(timezone.utc).isoformat(),
                            raw_data={'json_extraction': True, 'page': page_num}
                        )
                        
                        # Validate before adding
                        is_valid, error_msg = self.validate_listing(listing)
                        if is_valid:
                            listings.append(listing)
                        else:
                            logger.warning(f"  ❌ Rejected: {error_msg} | {title[:40]}... | {price_eur}€ | {location}")
                        
                    except Exception as e:
                        logger.warning(f"  ⚠️  Error parsing listing: {e}")
                        continue
                
                logger.info(f"  ✅ Page {page_num}: {len(listings)} valid listings")
                
        except Exception as e:
            logger.error(f"Error scraping Storia JSON: {e}")
        
        return listings

    async def scrape_storia_bulk(self, page: Page = None) -> List[Listing]:
        """Bulk scrape Storia.ro using JSON extraction (no browser needed)."""
        logger.info(f"🕵️  Bulk scraping Storia.ro (max {self.config.max_pages} pages) via JSON...")
        all_listings = []
        
        for page_num in range(1, self.config.max_pages + 1):
            if len(all_listings) >= self.config.max_listings_total:
                logger.info(f"⛔ Reached max listings limit: {self.config.max_listings_total}")
                break
            
            # Scrape this page
            page_listings = await self.scrape_storia_json(page_num)
            
            if not page_listings:
                logger.info("  ✅ No more listings available")
                break
            
            all_listings.extend(page_listings)
            logger.info(f"  📊 Total so far: {len(all_listings)} listings")
            
            # Rate limiting between pages
            if page_num < self.config.max_pages:
                await asyncio.sleep(self.config.rate_limit_delay)
        
        logger.info(f"✅ Storia.ro bulk complete: {len(all_listings)} listings")
        return all_listings
    
    async def run(self, config: Optional[ScrapingConfig] = None):
        """Main scraping loop - BULK MODE for 6 months of data."""
        if config:
            self.config = config
        
        logger.info("="*60)
        logger.info("🏠 CASA HUNT - SCOUT AGENT - BULK MODE")
        logger.info(f"📄 Max pages per source: {self.config.max_pages}")
        logger.info(f"📦 Batch size: {self.config.batch_size}")
        logger.info(f"🎯 Max listings: {self.config.max_listings_total}")
        logger.info("="*60)
        
        start_time = datetime.now(timezone.utc)
        total_new_listings = 0
        all_listings = []
        
        try:
            # Scrape Storia.ro using JSON method (fast, no browser needed)
            logger.info("\n🕵️  Starting Storia.ro bulk scrape (JSON method)...")
            storia_listings = await self.scrape_storia_bulk()
            all_listings.extend(storia_listings)
            
            # Try Imobiliare.ro with httpx + saved cookies (no Playwright needed)
            logger.info("\n🕵️  Starting Imobiliare.ro bulk scrape (httpx + saved cookies)...")
            if not state_file_exists():
                logger.warning("⚠️  imobiliare_state.json not found — run setup_imobiliare.py first. Skipping Imobiliare.ro.")
            else:
                if needs_refresh():
                    logger.warning("⚠️  imobiliare_state.json is older than 12 hours — consider re-running setup_imobiliare.py")
                try:
                    imobiliare_listings = await self.scrape_imobiliare_bulk()
                    all_listings.extend(imobiliare_listings)
                except Exception as e:
                    logger.error(f"Imobiliare scraping error: {e}")
                
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            import traceback
            traceback.print_exc()
        
        # Process in batches
        if all_listings:
            logger.info(f"\n💾 Processing {len(all_listings)} total listings...")
            
            # Convert to dicts
            listing_dicts = [asdict(l) for l in all_listings]
            
            # Check for duplicates in batches
            urls = [l.url for l in all_listings]
            existing = self.db.get_existing_urls(urls)
            
            new_listings = [l for l in listing_dicts if l['url'] not in existing]
            # Deduplicate by URL within the batch (same listing can appear on multiple pages)
            seen_urls = set()
            deduped = []
            for l in new_listings:
                if l['url'] not in seen_urls:
                    seen_urls.add(l['url'])
                    deduped.append(l)
            new_listings = deduped
            logger.info(f"📊 Found {len(existing)} duplicates, {len(new_listings)} new listings")
            
            if new_listings:
                # Process in batches
                batch_size = self.config.batch_size
                total_inserted = 0
                
                for i in range(0, len(new_listings), batch_size):
                    batch = new_listings[i:i+batch_size]
                    inserted_ids = self.db.insert_listings(batch)
                    total_inserted += len(inserted_ids)
                    logger.info(f"  ✅ Batch {i//batch_size + 1}: Inserted {len(inserted_ids)} listings")
                
                logger.info(f"\n🎉 Total inserted: {total_inserted} listings")
                
                # Create events and missions
                self.db.create_event('listings_scraped', {
                    'count': total_inserted,
                    'sources': list(set(l['source'] for l in new_listings)),
                    'timestamp': start_time.isoformat(),
                    'mode': 'bulk'
                })
                
                # Create analyze missions in batches
                all_ids = [l['id'] for l in new_listings if 'id' in l]
                for i in range(0, len(all_ids), batch_size):
                    batch_ids = all_ids[i:i+batch_size]
                    self.db.create_mission('analyze', 'pending', {
                        'listing_ids': batch_ids,
                        'count': len(batch_ids),
                        'batch': i//batch_size + 1
                    })
                
                logger.info(f"🎯 Created {len(range(0, len(all_ids), batch_size))} analyze missions")
                
                logger.info(f"🎯 Created analyze mission for {len(inserted_ids)} listings")
            else:
                logger.info("No new listings to save")
        
        # Log agent state
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        self.db.log_agent_state('scout', 'completed', {
            'listings_found': len(all_listings),
            'new_listings': len(new_listings) if all_listings else 0,
            'duration_seconds': duration,
            'sources': ['imobiliare.ro', 'storia.ro']
        })
        
        logger.info("="*60)
        logger.info(f"✅ SCOUT COMPLETE in {duration:.1f}s")
        logger.info("="*60)
        
        return all_listings


async def main():
    """Entry point for running scout standalone."""
    agent = ScoutAgent()
    await agent.run()


if __name__ == '__main__':
    asyncio.run(main())
