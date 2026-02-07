#!/usr/bin/env python3
"""Full pipeline test - scrape, analyze, decide, notify."""

import asyncio
import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from scout_agent import ScoutAgent
from analyzer_agent import AnalyzerAgent
from decision_agent import DecisionAgent
from notifier_agent import NotifierAgent
from supabase_manager import SupabaseManager

async def full_pipeline_test():
    """Run full pipeline and send Telegram notification."""
    print("🏠 CASA HUNT - Full Pipeline Test")
    print("="*60)
    
    db = SupabaseManager()
    
    # Step 1: Scout - scrape Storia
    print("\n🕵️  STEP 1: Scraping Storia.ro...")
    scout = ScoutAgent()
    listings = await scout.scrape_storia_json(page_num=1)
    print(f"✅ Scraped {len(listings)} listings")
    
    if not listings:
        print("❌ No listings found!")
        return
    
    # Save to database
    from dataclasses import asdict
    listing_dicts = [asdict(l) for l in listings]
    inserted_ids = db.insert_listings(listing_dicts)
    print(f"✅ Saved {len(inserted_ids)} listings to database")
    
    # Step 2: Analyzer - score listings
    print("\n🤖 STEP 2: Analyzing listings...")
    analyzer = AnalyzerAgent()
    
    analyzed = []
    for listing in listings[:3]:  # Analyze first 3
        # Convert to dict for analyzer
        listing_dict = {
            'price_eur': listing.price_eur,
            'surface_mp': listing.surface_mp,
            'location': listing.location,
            'title': listing.title,
            'url': listing.url
        }
        
        score = analyzer.calculate_score(listing_dict)
        
        # Get breakdown for display
        price_score = analyzer.calculate_price_per_mp_score(listing.price_eur, listing.surface_mp)
        metro_score = analyzer.calculate_metro_score(listing.location, listing.title)
        location_score = analyzer.calculate_location_score(listing.location)
        budget_score = analyzer.calculate_budget_score(listing.price_eur or 0)
        
        score_data = {
            'total_score': score,
            'breakdown': {
                'price_per_mp': price_score,
                'metro': metro_score,
                'location': location_score,
                'budget': budget_score
            }
        }
        
        # Save analysis
        db.client.table('listings').update({
            'score': score,
            'analyzed_at': datetime.now(timezone.utc).isoformat()
        }).eq('external_id', listing.external_id).execute()
        
        analyzed.append({
            'listing': listing,
            'score': score_data
        })
        print(f"  📊 {listing.title[:40]}... → {score}/100")
    
    # Step 3: Decision - approve/reject
    print("\n⚖️  STEP 3: Making decisions...")
    decision_agent = DecisionAgent()
    notifier = NotifierAgent()
    
    approved = []
    for item in analyzed:
        listing = item['listing']
        score = item['score']['total_score']
        
        # Convert to dict for decision agent
        listing_dict = {
            'score': score,
            'price_eur': listing.price_eur,
            'location': listing.location,
            'title': listing.title,
            'features_raw': listing.features_raw
        }
        
        decision_result = decision_agent.make_decision(listing_dict)
        decision = {'decision': decision_result[0], 'reason': decision_result[1]}
        
        print(f"  {'✅' if decision['decision'] == 'APPROVE' else '❌'} {listing.title[:40]}... → {decision['decision']}")
        
        if decision['decision'] == 'APPROVE':
            approved.append(item)
    
    # Step 4: Notify - send Telegram
    print("\n📱 STEP 4: Sending Telegram notifications...")
    
    if approved:
        for item in approved:
            listing = item['listing']
            score = item['score']
            
            # Format message
            message = notifier.format_telegram_message(
                {
                    'title': listing.title,
                    'price_eur': listing.price_eur,
                    'location': listing.location,
                    'surface_mp': listing.surface_mp,
                    'score': score['total_score'],
                    'url': listing.url
                },
                f"Price/mp: {score['breakdown'].get('price_per_mp', 0):.0f}€, Location: {score['breakdown'].get('location_bonus', 0)}pts"
            )
            
            result = await notifier.send_telegram(message)
            
            if result:
                print(f"  ✅ Telegram sent: {listing.title[:40]}...")
            else:
                print(f"  ❌ Telegram failed: {listing.title[:40]}...")
    else:
        print("  ℹ️ No approved listings to notify")
    
    print("\n" + "="*60)
    print(f"🎉 Pipeline complete! Scraped {len(listings)}, analyzed {len(analyzed)}, approved {len(approved)}")
    print("="*60)

if __name__ == '__main__':
    asyncio.run(full_pipeline_test())
