#!/usr/bin/env python3
"""
Casa Hunt - Alternative Scout Agent
Uses multiple methods to bypass anti-bot protection
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import json
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional
from urllib.parse import urljoin

# Try different approaches
import requests
from bs4 import BeautifulSoup

# Setup logging
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'scout_alt.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('scout_alt')


class AlternativeScout:
    """Alternative scraping methods."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
    
    def fetch_with_requests(self, url: str) -> Optional[str]:
        """Try to fetch page with requests."""
        try:
            logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Requests failed: {e}")
            return None
    
    def parse_imobiliare_html(self, html: str) -> List[Dict]:
        """Parse Imobiliare.ro HTML."""
        listings = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try multiple selectors
        selectors = [
            '.box-anunt',
            '[data-testid="listing-card"]',
            '.listing-item',
            '.property-card',
            'article',
            '.anunt',
        ]
        
        cards = []
        for selector in selectors:
            cards = soup.select(selector)
            if cards:
                logger.info(f"Found {len(cards)} cards with selector: {selector}")
                break
        
        if not cards:
            # Try to find any div that looks like a listing
            cards = soup.find_all('div', class_=re.compile(r'(anunt|listing|property|card)', re.I))
            logger.info(f"Found {len(cards)} cards with regex search")
        
        for card in cards[:5]:  # Test with first 5
            try:
                listing = {
                    'title': self._extract_text(card, ['h2', 'h3', '.title', '[data-testid="title"]']),
                    'price': self._extract_text(card, ['.pret', '.price', '[data-testid="price"]']),
                    'location': self._extract_text(card, ['.locatie', '.location', '[data-testid="location"]']),
                    'url': self._extract_url(card),
                }
                if listing['title']:
                    listings.append(listing)
                    logger.info(f"Parsed: {listing['title'][:50]}...")
            except Exception as e:
                logger.warning(f"Error parsing card: {e}")
        
        return listings
    
    def _extract_text(self, element, selectors: List[str]) -> str:
        """Try multiple selectors to extract text."""
        for selector in selectors:
            try:
                found = element.select_one(selector)
                if found:
                    return found.get_text(strip=True)
            except:
                continue
        return ""
    
    def _extract_url(self, element) -> str:
        """Extract URL from element."""
        try:
            link = element.find('a')
            if link:
                return link.get('href', '')
        except:
            pass
        return ""
    
    def save_sample_html(self, url: str, filename: str):
        """Save sample HTML for analysis."""
        html = self.fetch_with_requests(url)
        if html:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"Saved HTML sample to: {filename}")
            return True
        return False
    
    async def test_all_methods(self):
        """Test all scraping methods."""
        logger.info("="*60)
        logger.info("🧪 TESTING ALTERNATIVE SCRAPING METHODS")
        logger.info("="*60)
        
        urls = [
            "https://www.imobiliare.ro/vanzare-case-vile/bucuresti?pretmax=200000",
            "https://www.storia.ro/ro/cautare/vanzare/casa/vila/bucuresti?priceMax=200000",
        ]
        
        for url in urls:
            logger.info(f"\n🌐 Testing: {url}")
            
            # Method 1: Direct requests
            html = self.fetch_with_requests(url)
            if html:
                logger.info(f"  ✅ Got HTML ({len(html)} chars)")
                
                # Save sample
                filename = f"/tmp/sample_{url.split('/')[2]}.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html[:5000])  # First 5000 chars
                logger.info(f"  💾 Sample saved to {filename}")
                
                # Try to parse
                listings = self.parse_imobiliare_html(html)
                logger.info(f"  📊 Parsed {len(listings)} listings")
                
                if listings:
                    for i, l in enumerate(listings[:3]):
                        logger.info(f"    {i+1}. {l.get('title', 'N/A')[:40]}...")
            else:
                logger.error("  ❌ Failed to fetch")
        
        logger.info("\n" + "="*60)
        logger.info("✅ Testing complete")
        logger.info("="*60)


if __name__ == '__main__':
    scout = AlternativeScout()
    asyncio.run(scout.test_all_methods())
