#!/usr/bin/env python3
"""
Casa Hunt - Advanced House Scraper with Playwright
Handles JavaScript-rendered sites like Imobiliare.ro and Storia.ro
"""

import json
import os
import re
import hashlib
import asyncio
from datetime import datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright

class CasaHuntScraper:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.seen_urls = set()
        self.load_seen_urls()
        
    def load_seen_urls(self):
        """Load previously seen URLs"""
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
        cleaned = re.sub(r'[^\d]', '', price_text)
        return int(cleaned) if cleaned else None
    
    def extract_surface(self, text):
        """Extract surface area"""
        if not text:
            return None
        match = re.search(r'(\d+)\s*(?:mp|m²)', text.lower())
        return int(match.group(1)) if match else None
    
    async def scrape_imobiliare(self, page, max_pages=2):
        """Scrape Imobiliare.ro"""
        listings = []
        base_url = "https://www.imobiliare.ro"
        
        for page_num in range(1, max_pages + 1):
            url = f"{base_url}/vanzare-case-vile/bucuresti?pret-max=990000&pagina={page_num}"
            print(f"Scraping Imobiliare page {page_num}...")
            
            try:
                await page.goto(url, wait_until='networkidle', timeout=60000)
                await page.wait_for_timeout(3000)  # Wait for JS to load
                
                # Accept cookies if present
                try:
                    cookie_btn = await page.query_selector('button:has-text("Accept"), button:has-text("Acord"), #cookieAccept')
                    if cookie_btn:
                        await cookie_btn.click()
                        await page.wait_for_timeout(1000)
                except:
                    pass
                
                # Extract listings using page.evaluate for better performance
                page_listings = await page.evaluate('''() => {
                    const listings = [];
                    const cards = document.querySelectorAll('.box-anunt, .anunt, [data-testid="listing-card"]');
                    
                    cards.forEach(card => {
                        const data = {};
                        
                        // Link
                        const link = card.querySelector('a[href*="/vanzare"]');
                        if (link) {
                            data.url = link.href;
                            data.title = link.textContent.trim();
                        }
                        
                        // Price
                        const price = card.querySelector('.pret, .price, [class*="pret"]');
                        if (price) {
                            data.price_raw = price.textContent.trim();
                        }
                        
                        // Location
                        const loc = card.querySelector('.locatie, .location, [class*="locatie"]');
                        if (loc) {
                            data.location = loc.textContent.trim();
                        }
                        
                        // Features
                        const features = card.querySelector('.caracteristici, .features');
                        if (features) {
                            data.features = features.textContent.trim();
                        }
                        
                        listings.push(data);
                    });
                    
                    return listings;
                }''')
                
                for item in page_listings:
                    if not item.get('url') or item['url'] in self.seen_urls:
                        continue
                    
                    listing = {
                        'source': 'imobiliare.ro',
                        'id': hashlib.md5(item['url'].encode()).hexdigest()[:12],
                        'url': item['url'],
                        'title': item.get('title', 'N/A')[:200],
                        'price_raw': item.get('price_raw', ''),
                        'price_eur': self.clean_price(item.get('price_raw', '')),
                        'location': item.get('location', 'N/A'),
                        'surface_mp': self.extract_surface(item.get('features', '')),
                        'features_raw': item.get('features', ''),
                        'scraped_at': datetime.now().isoformat()
                    }
                    
                    # Filter under 200k
                    if listing['price_eur'] and listing['price_eur'] <= 200000:
                        listings.append(listing)
                        self.save_seen_url(listing['url'])
                
                print(f"Found {len(page_listings)} listings on page {page_num}")
                
                if len(page_listings) == 0:
                    break
                    
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"Error on page {page_num}: {e}")
                break
        
        return listings
    
    async def scrape_storia(self, page, max_pages=2):
        """Scrape Storia.ro"""
        listings = []
        base_url = "https://www.storia.ro"
        
        for page_num in range(1, max_pages + 1):
            url = f"{base_url}/ro/rezultate/vanzare/casa/bucuresti?limit=36&page={page_num}&priceMax=200000"
            print(f"Scraping Storia page {page_num}...")
            
            try:
                await page.goto(url, wait_until='networkidle', timeout=60000)
                await page.wait_for_timeout(3000)
                
                # Accept cookies
                try:
                    cookie_btn = await page.query_selector('button:has-text("Accept"), #onetrust-accept-btn-handler')
                    if cookie_btn:
                        await cookie_btn.click()
                        await page.wait_for_timeout(1000)
                except:
                    pass
                
                page_listings = await page.evaluate('''() => {
                    const listings = [];
                    const cards = document.querySelectorAll('[data-cy="listing-item"], article, .offer-item');
                    
                    cards.forEach(card => {
                        const data = {};
                        
                        const link = card.querySelector('a[href*="/oferta/"]');
                        if (link) {
                            data.url = link.href;
                        }
                        
                        const title = card.querySelector('h3, [data-testid="listing-title"]');
                        if (title) {
                            data.title = title.textContent.trim();
                        }
                        
                        const price = card.querySelector('[aria-label*="price"], .price, [data-testid="listing-price"]');
                        if (price) {
                            data.price_raw = price.textContent.trim();
                        }
                        
                        const loc = card.querySelector('[aria-label*="location"], .location');
                        if (loc) {
                            data.location = loc.textContent.trim();
                        }
                        
                        const rooms = card.querySelector('[aria-label*="rooms"], .rooms');
                        if (rooms) {
                            data.rooms = rooms.textContent.trim();
                        }
                        
                        listings.push(data);
                    });
                    
                    return listings;
                }''')
                
                for item in page_listings:
                    if not item.get('url') or item['url'] in self.seen_urls:
                        continue
                    
                    listing = {
                        'source': 'storia.ro',
                        'id': hashlib.md5(item['url'].encode()).hexdigest()[:12],
                        'url': item['url'],
                        'title': item.get('title', 'N/A')[:200],
                        'price_raw': item.get('price_raw', ''),
                        'price_eur': self.clean_price(item.get('price_raw', '')),
                        'location': item.get('location', 'N/A'),
                        'scraped_at': datetime.now().isoformat()
                    }
                    
                    if listing['price_eur'] and listing['price_eur'] <= 200000:
                        listings.append(listing)
                        self.save_seen_url(listing['url'])
                
                print(f"Found {len(page_listings)} listings on page {page_num}")
                
                if len(page_listings) == 0:
                    break
                
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"Error on page {page_num}: {e}")
                break
        
        return listings
    
    def has_metro_access(self, location_text):
        """Check if location mentions metro"""
        metro_keywords = ['metrou', 'statie', 'pipera', 'universitate', 'romana', 
                         'victoriei', 'pallady', 'berceni', 'dimitrie', 'leonida']
        return any(kw in location_text.lower() for kw in metro_keywords)
    
    async def run(self):
        """Main scraping routine"""
        print("Starting Casa Hunt scraper with Playwright...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            all_listings = []
            
            # Scrape both sources
            print("\nScraping Imobiliare.ro...")
            imobiliare_listings = await self.scrape_imobiliare(page, max_pages=2)
            all_listings.extend(imobiliare_listings)
            print(f"Total from Imobiliare: {len(imobiliare_listings)}")
            
            print("\nScraping Storia.ro...")
            storia_listings = await self.scrape_storia(page, max_pages=2)
            all_listings.extend(storia_listings)
            print(f"Total from Storia: {len(storia_listings)}")
            
            await browser.close()
            
            # Mark metro proximity
            for listing in all_listings:
                listing['metro_nearby'] = self.has_metro_access(listing.get('location', ''))
            
            # Filter for Bucharest area
            bucharest_listings = [
                l for l in all_listings 
                if any(kw in l.get('location', '').lower() for kw in 
                       ['bucuresti', 'ilfov', 'berceni', 'bragadiru', 'popesti', 'chiajna'])
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
                    "property_type": "houses/villas"
                },
                "listings": bucharest_listings
            }
            
            os.makedirs(self.output_dir, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            print(f"\n{'='*50}")
            print("CASA HUNT - SCRAPING COMPLETE")
            print(f"{'='*50}")
            print(f"Total listings: {len(all_listings)}")
            print(f"Bucharest/Ilfov: {len(bucharest_listings)}")
            print(f"Metro nearby: {result['metro_accessible']}")
            print(f"Budget <200k: {len([l for l in bucharest_listings if l.get('price_eur', 0) <= 200000])}")
            print(f"{'='*50}")
            print(f"Saved to: {output_file}")
            
            return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Casa Hunt - House Scraper')
    parser.add_argument('--output-dir', required=True, help='Output directory')
    args = parser.parse_args()
    
    scraper = CasaHuntScraper(args.output_dir)
    asyncio.run(scraper.run())


if __name__ == '__main__':
    main()
