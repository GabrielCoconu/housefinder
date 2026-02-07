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
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from supabase_manager import SupabaseManager

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
    max_pages: int = 3
    max_price: int = 200000
    min_price: int = 100000
    location: str = "bucuresti"
    listing_type: str = "case-vile"  # houses/villas


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
        """Parse price text to raw and EUR values."""
        if not price_text:
            return "", None
        
        price_clean = re.sub(r'[^\d.,]', '', price_text).replace(',', '.')
        
        try:
            if 'ron' in price_text.lower() or 'lei' in price_text.lower():
                price_ron = float(price_clean)
                price_eur = int(price_ron / self.eur_rate)
            else:
                # Assume EUR
                price_eur = int(float(price_clean))
            
            return price_text.strip(), price_eur
        except (ValueError, TypeError):
            return price_text.strip(), None
    
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
    
    def validate_listing(self, listing: Dict) -> tuple[bool, str]:
        """Validate listing before saving. Returns (is_valid, error_message)."""
        url = listing.get('url', '')
        price = listing.get('price_eur')
        location = listing.get('location', '')
        
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
        
        # Reject generic location
        if location.lower().strip() == 'bucuresti':
            return False, "Location too generic (just 'Bucuresti')"
        
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
    
    async def run(self, config: Optional[ScrapingConfig] = None):
        """Main scraping loop."""
        if config:
            self.config = config
        
        logger.info("="*60)
        logger.info("🏠 CASA HUNT - SCOUT AGENT STARTING")
        logger.info("="*60)
        
        start_time = datetime.now(timezone.utc)
        all_listings: List[Listing] = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            try:
                # Scrape both sources
                imobiliare_listings = await self.scrape_imobiliare(page)
                storia_listings = await self.scrape_storia(page)
                
                all_listings = imobiliare_listings + storia_listings
                
            except Exception as e:
                logger.error(f"Scraping error: {e}")
            
            finally:
                await browser.close()
        
        # Save to Supabase
        if all_listings:
            logger.info(f"💾 Saving {len(all_listings)} listings to Supabase...")
            
            # Convert to dicts
            listing_dicts = [asdict(l) for l in all_listings]
            
            # Check for duplicates
            urls = [l.url for l in all_listings]
            existing = self.db.get_existing_urls(urls)
            
            new_listings = [l for l in listing_dicts if l['url'] not in existing]
            logger.info(f"Found {len(existing)} duplicates, {len(new_listings)} new listings")
            
            if new_listings:
                # Insert to Supabase
                inserted_ids = self.db.insert_listings(new_listings)
                logger.info(f"✅ Inserted {len(inserted_ids)} listings")
                
                # Create event
                self.db.create_event('listings_scraped', {
                    'count': len(inserted_ids),
                    'sources': list(set(l['source'] for l in new_listings)),
                    'timestamp': start_time.isoformat()
                })
                
                # Create analyze missions
                self.db.create_mission('analyze', 'pending', {
                    'listing_ids': inserted_ids,
                    'count': len(inserted_ids)
                })
                
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
