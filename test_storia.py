#!/usr/bin/env python3
"""Test script for Storia JSON scraper."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from scout_agent import ScoutAgent

async def test_storia_json():
    """Test the Storia JSON scraper."""
    agent = ScoutAgent()
    
    print("🧪 Testing Storia.ro JSON scraper...")
    print("="*60)
    
    # Test single page
    listings = await agent.scrape_storia_json(page_num=1)
    
    print("\n" + "="*60)
    print(f"✅ Found {len(listings)} valid listings")
    print("="*60)
    
    # Show first 3 listings
    for i, listing in enumerate(listings[:3], 1):
        print(f"\n📍 Listing {i}:")
        print(f"   Title: {listing.title}")
        print(f"   Price: {listing.price_raw} ({listing.price_eur}€)")
        print(f"   Location: {listing.location}")
        print(f"   Surface: {listing.surface_mp}mp")
        print(f"   Rooms: {listing.rooms}")
        print(f"   URL: {listing.url}")
        print(f"   Metro nearby: {'✅' if listing.metro_nearby else '❌'}")
    
    return listings

if __name__ == '__main__':
    listings = asyncio.run(test_storia_json())
    print(f"\n🎉 Test complete! Scraped {len(listings)} listings from Storia.ro")
