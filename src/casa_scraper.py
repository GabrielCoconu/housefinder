#!/usr/bin/env python3
"""
Casa Hunt - Robust House Listings Scraper
Scrape Imobiliare.ro and Storia.ro for houses in Bucharest periphery with metro access
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
import random
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HouseScraper:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ro;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
        })
        self.seen_urls = set()
        self.load_seen_urls()
        
    def load_seen_urls(self):
        """Load previously seen URLs to avoid duplicates"""
        seen_file = os.path.join(self.output_dir, '.seen_urls')
        if os.path.exists(seen_file):
            with open(seen_file, 'r') as f:
                self.seen_urls = set(line.strip() for line in f)
        
    def save_seen_url(self, url):
        """Save URL to deduplication file"""
        seen_file = os.path.join(self.output_dir, '.seen_urls')
        with open(seen_file, 'a') as f:
            f.write(f"{url}\n")
        self.seen_urls.add(url)
        
    def clean_price(self, price_text):
        """Extract numeric price from text"""
        if not price_text:
            return None
        # Remove currency symbols and extract number
        cleaned = re.sub(r'[^\d]', '', price_text)
        return int(cleaned) if cleaned else None
        
    def extract_surface(self, text):
        """Extract surface area in mp"""
        if not text:
            return None
        match = re.search(r'(\d+)\s*mp', text.lower())
        return int(match.group(1)) if match else None
        
    def extract_rooms(self, text):
        """Extract number of rooms"""
        if not text:
            return None
        match = re.search(r'(\d+)\s*(?:cam|camera)', text.lower())
        return int(match.group(1)) if match else None

    def scrape_imobiliare(self, max_pages=3):
        """Scrape Imobiliare.ro for houses in Bucharest"""
        listings = []
        base_url = "https://www.imobiliare.ro"
        
        # Search URL for houses in Bucharest, max 990,000 EUR (approx 200k)
        search_paths = [
            "/vanzare-case-vile/bucuresti?pret-max=990000",  # All sectors
        ]
        
        for path in search_paths:
            for page in range(1, max_pages + 1):
                url = f"{base_url}{path}&pagina={page}"
                logger.info(f"Fetching: {url}")
                
                try:
                    response = self.session.get(url, timeout=30)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Find listing cards - multiple possible selectors
                    cards = soup.find_all('div', class_=re.compile('box-anunt|listing|property'))
                    
                    if not cards:
                        logger.warning(f"No listings found on page {page}")
                        break
                    
                    for card in cards:
                        try:
                            listing = self.parse_imobiliare_card(card, base_url)
                            if listing and listing['url'] not in self.seen_urls:
                                listings.append(listing)
                                self.save_seen_url(listing['url'])
                        except Exception as e:
                            logger.error(f"Error parsing card: {e}")
                            continue
                    
                    # Random delay to be polite
                    time.sleep(random.uniform(1, 3))
                    
                except requests.RequestException as e:
                    logger.error(f"Request failed: {e}")
                    break
                    
        return listings
        
    def parse_imobiliare_card(self, card, base_url):
        """Parse a single listing card from Imobiliare.ro"""
        listing = {
            'source': 'imobiliare.ro',
            'scraped_at': datetime.now().isoformat(),
        }
        
        # Extract link
        link_elem = card.find('a', href=re.compile('/vanzare'))
        if link_elem:
            href = link_elem.get('href', '')
            listing['url'] = urljoin(base_url, href) if not href.startswith('http') else href
            listing['id'] = hashlib.md5(listing['url'].encode()).hexdigest()[:12]
        else:
            return None
            
        # Extract title
        title_elem = card.find(['h2', 'h3', 'a'], class_=re.compile('titlu|title'))
        listing['title'] = title_elem.get_text(strip=True) if title_elem else 'N/A'
        
        # Extract price
        price_elem = card.find(['div', 'span', 'p'], class_=re.compile('pret|price'))
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            listing['price_raw'] = price_text
            listing['price_eur'] = self.clean_price(price_text)
        
        # Extract location
        loc_elem = card.find(['div', 'span'], class_=re.compile('locatie|location'))
        listing['location'] = loc_elem.get_text(strip=True) if loc_elem else 'N/A'
        
        # Extract features (surface, rooms)
        features_elem = card.find(['div', 'span'], class_=re.compile('caracteristici|features'))
        if features_elem:
            features_text = features_elem.get_text(strip=True)
            listing['surface_mp'] = self.extract_surface(features_text)
            listing['rooms'] = self.extract_rooms(features_text)
            listing['features_raw'] = features_text
        
        # Extract description
        desc_elem = card.find(['div', 'p'], class_=re.compile('descriere|description'))
        listing['description'] = desc_elem.get_text(strip=True)[:500] if desc_elem else ''
        
        # Filter: only houses under 200k EUR in Bucharest periphery
        if listing.get('price_eur') and listing['price_eur'] > 200000:
            return None
            
        if 'bucuresti' not in listing.get('location', '').lower() and 'ilfov' not in listing.get('location', '').lower():
            # Might still be valid, keep it and let user decide
            pass
            
        return listing

    def scrape_storia(self, max_pages=3):
        """Scrape Storia.ro for houses in Bucharest"""
        listings = []
        base_url = "https://www.storia.ro"
        
        # Search for houses in Bucharest, max price 200,000 EUR
        # Note: Storia uses filters in URL parameters
        search_urls = [
            f"{base_url}/ro/rezultate/vanzare/casa/bucuresti?limit=36&page={{page}}&priceMax=200000",
        ]
        
        for search_template in search_urls:
            for page in range(1, max_pages + 1):
                url = search_template.format(page=page)
                logger.info(f"Fetching: {url}")
                
                try:
                    response = self.session.get(url, timeout=30)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Storia listing cards
                    cards = soup.find_all('article', {'data-cy': 'listing-item'})
                    if not cards:
                        cards = soup.find_all('div', class_=re.compile('offer|listing'))
                    
                    if not cards:
                        logger.warning(f"No listings found on page {page}")
                        break
                    
                    for card in cards:
                        try:
                            listing = self.parse_storia_card(card, base_url)
                            if listing and listing['url'] not in self.seen_urls:
                                listings.append(listing)
                                self.save_seen_url(listing['url'])
                        except Exception as e:
                            logger.error(f"Error parsing Storia card: {e}")
                            continue
                    
                    time.sleep(random.uniform(1, 3))
                    
                except requests.RequestException as e:
                    logger.error(f"Request failed: {e}")
                    break
                    
        return listings
        
    def parse_storia_card(self, card, base_url):
        """Parse a single listing card from Storia.ro"""
        listing = {
            'source': 'storia.ro',
            'scraped_at': datetime.now().isoformat(),
        }
        
        # Extract link
        link_elem = card.find('a', href=re.compile('/ro/oferta'))
        if link_elem:
            href = link_elem.get('href', '')
            listing['url'] = urljoin(base_url, href) if not href.startswith('http') else href
            listing['id'] = hashlib.md5(listing['url'].encode()).hexdigest()[:12]
        else:
            return None
            
        # Extract title
        title_elem = card.find(['h3', 'a'], class_=re.compile('title|titlu'))
        listing['title'] = title_elem.get_text(strip=True) if title_elem else 'N/A'
        
        # Extract price
        price_elem = card.find(['span', 'p'], class_=re.compile('price|pret'))
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            listing['price_raw'] = price_text
            listing['price_eur'] = self.clean_price(price_text)
        
        # Extract location
        loc_elem = card.find(['p', 'span'], class_=re.compile('location|locatie'))
        listing['location'] = loc_elem.get_text(strip=True) if loc_elem else 'N/A'
        
        # Extract rooms and surface
        rooms_elem = card.find(['span', 'div'], class_=re.compile('rooms|camere'))
        if rooms_elem:
            listing['rooms'] = self.extract_rooms(rooms_elem.get_text())
            
        surface_elem = card.find(['span', 'div'], class_=re.compile('area|mp|m²'))
        if surface_elem:
            listing['surface_mp'] = self.extract_surface(surface_elem.get_text())
        
        return listing

    def has_metro_access(self, location_text):
        """Check if location mentions metro access"""
        metro_keywords = ['metrou', 'statie', 'linia', 'm1', 'm2', 'm3', 'm4', 'm5', 
                         'pipera', 'universitate', 'romana', 'victoriei', 'pallady',
                         'berceni', 'dimitrie', 'leonida', 'tudor arghezi']
        location_lower = location_text.lower()
        return any(keyword in location_lower for keyword in metro_keywords)

    def run(self):
        """Main scraping routine"""
        logger.info("Starting Casa Hunt scraper...")
        
        all_listings = []
        
        # Scrape both sources
        logger.info("Scraping Imobiliare.ro...")
        imobiliare_listings = self.scrape_imobiliare(max_pages=2)
        all_listings.extend(imobiliare_listings)
        logger.info(f"Found {len(imobiliare_listings)} listings on Imobiliare.ro")
        
        logger.info("Scraping Storia.ro...")
        storia_listings = self.scrape_storia(max_pages=2)
        all_listings.extend(storia_listings)
        logger.info(f"Found {len(storia_listings)} listings on Storia.ro")
        
        # Mark metro proximity
        for listing in all_listings:
            listing['metro_nearby'] = self.has_metro_access(listing.get('location', ''))
        
        # Filter for Bucharest/Ilfov area
        bucharest_listings = [
            l for l in all_listings 
            if any(keyword in l.get('location', '').lower() for keyword in 
                   ['bucuresti', 'ilfov', 'berceni', 'bragadiru', 'popesti', 'chiajna', 'voluntari'])
        ]
        
        # Save results
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = os.path.join(self.output_dir, f"listings_{timestamp}.json")
        
        result = {
            "timestamp": timestamp,
            "total_listings": len(all_listings),
            "bucharest_listings": len(bucharest_listings),
            "metro_accessible": len([l for l in bucharest_listings if l.get('metro_nearby')]),
            "sources": ["imobiliare.ro", "storia.ro"],
            "criteria": {
                "location": "Bucharest + Ilfov periphery",
                "max_price_eur": 200000,
                "property_type": "houses/villas",
                "metro_access": "preferred"
            },
            "listings": bucharest_listings
        }
        
        os.makedirs(self.output_dir, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to: {output_file}")
        logger.info(f"Total listings: {len(all_listings)}")
        logger.info(f"Bucharest/Ilfov listings: {len(bucharest_listings)}")
        logger.info(f"With metro access: {result['metro_accessible']}")
        
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Casa Hunt - House Listings Scraper')
    parser.add_argument('--output-dir', required=True, help='Directory to save results')
    parser.add_argument('--test', action='store_true', help='Run in test mode (single page)')
    args = parser.parse_args()
    
    scraper = HouseScraper(args.output_dir)
    
    result = scraper.run()
    
    # Print summary
    print("\n" + "="*50)
    print("CASA HUNT - SCRAPING COMPLETE")
    print("="*50)
    print(f"Total listings found: {result['total_listings']}")
    print(f"Bucharest/Ilfov area: {result['bucharest_listings']}")
    print(f"With metro access: {result['metro_accessible']}")
    print(f"Budget <200k EUR: {len([l for l in result['listings'] if l.get('price_eur', 999999) <= 200000])}")
    print("="*50)
    
    return 0


if __name__ == '__main__':
    exit(main())
