#!/usr/bin/env python3
"""Quick test for Storia JSON scraper - single page only."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from scout_agent import ScoutAgent

async def test():
    agent = ScoutAgent()
    
    print("🧪 Testing Storia.ro JSON scraper...")
    print("="*60)
    
    # Test single page
    listings = await agent.scrape_storia_json(page_num=1)
    
    print("\n" + "="*60)
    print(f"✅ Found {len(listings)} valid listings")
    print("="*60)
    
    # Show all listings
    for i, listing in enumerate(listings, 1):
        print(f"\n📍 Listing {i}: {listing.title[:50]}...")
        print(f"   💰 {listing.price_eur}€ | 📐 {listing.surface_mp}mp | 🏠 {listing.rooms} camere")
        print(f"   📍 {listing.location}")
        print(f"   🔗 {listing.url[:70]}...")
    
    print(f"\n🎉 Test complete! Scraped {len(listings)} listings from Storia.ro")

if __name__ == '__main__':
    asyncio.run(test())
