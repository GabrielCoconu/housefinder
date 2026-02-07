#!/usr/bin/env python3
"""
Casa Hunt - Analyzer Agent
Scores listings based on multiple criteria
"""

import os
import sys

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
from supabase_manager import SupabaseManager

# Setup logging to file
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'analyzer.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('analyzer_agent')


class AnalyzerAgent:
    """Analyzes listings and calculates quality scores."""
    
    def __init__(self):
        self.db = SupabaseManager()
        self.max_price = 200000
        self.target_sectors = ['3', '4', '5', '6']
        self.metro_keywords = [
            'metrou', 'statie', 'pipera', 'universitate', 'romana',
            'victoriei', 'pallady', 'berceni', 'dimitrie', 'leonida',
            'titan', 'obor', 'muncii', 'timpuri noi'
        ]
    
    def calculate_price_per_mp_score(self, price_eur: int, surface_mp: Optional[int]) -> int:
        """Score based on price per square meter (lower = better)."""
        if not price_eur or not surface_mp or surface_mp == 0:
            return 20  # Neutral score if unknown
        
        price_per_mp = price_eur / surface_mp
        
        # Scoring: ≤1000€/mp = 40pts, ≤1500€/mp = 30pts, ≤2000€/mp = 20pts, ≤2500€/mp = 10pts
        if price_per_mp <= 1000:
            return 40
        elif price_per_mp <= 1500:
            return 30
        elif price_per_mp <= 2000:
            return 20
        elif price_per_mp <= 2500:
            return 10
        else:
            return 5
    
    def calculate_metro_score(self, location: str, title: str = "") -> int:
        """Score based on metro proximity (30 points max)."""
        text = f"{location} {title}".lower()
        
        # Check for metro keywords
        if any(kw in text for kw in self.metro_keywords):
            return 30
        
        return 0
    
    def calculate_location_score(self, location: str) -> int:
        """Score based on location quality (20 points max)."""
        location_lower = location.lower()
        
        # Good sectors: 3, 4, 5, 6
        if any(f'sector {s}' in location_lower or f'sector{s}' in location_lower 
               for s in self.target_sectors):
            return 20
        
        # Ilfov areas
        if any(area in location_lower for area in ['ilfov', 'voluntari', 'otopeni', 'popesti']):
            return 15
        
        # Other Bucharest areas
        if 'bucuresti' in location_lower:
            return 10
        
        return 0
    
    def calculate_budget_score(self, price_eur: int) -> int:
        """Score based on being under budget (10 points max)."""
        if not price_eur:
            return 0
        
        if price_eur <= 150000:
            return 10  # Well under budget
        elif price_eur <= 180000:
            return 7   # Comfortably under
        elif price_eur <= 200000:
            return 5   # At budget limit
        else:
            return 0   # Over budget
    
    def calculate_score(self, listing: Dict) -> int:
        """Calculate total score for a listing (max 100 points)."""
        price_eur = listing.get('price_eur')
        surface_mp = listing.get('surface_mp')
        location = listing.get('location', '')
        title = listing.get('title', '')
        
        # Calculate individual scores
        price_score = self.calculate_price_per_mp_score(price_eur, surface_mp)
        metro_score = self.calculate_metro_score(location, title)
        location_score = self.calculate_location_score(location)
        budget_score = self.calculate_budget_score(price_eur)
        
        total_score = price_score + metro_score + location_score + budget_score
        
        # Clamp score to 0-100 range (QA validation)
        total_score = max(0, min(100, total_score))
        
        logger.info(f"Score breakdown for {listing.get('url', 'N/A')[:50]}...")
        logger.info(f"  Price/mp: {price_score}/40, Metro: {metro_score}/30, Location: {location_score}/20, Budget: {budget_score}/10")
        logger.info(f"  Total: {total_score}/100")
        
        return total_score
    
    async def run(self):
        """Main agent loop."""
        logger.info("🧠 Analyzer Agent starting...")
        
        try:
            # Get pending analyze missions
            missions = self.db.get_pending_missions('analyze')
            
            if not missions:
                logger.info("No pending analyze missions")
                # Also check for unscored listings
                listings = self.db.get_unscored_listings()
                if not listings:
                    logger.info("No unscored listings found")
                    return
            else:
                # Extract listing IDs from missions
                listing_ids = []
                for mission in missions:
                    payload = mission.get('payload', {})
                    listing_ids.extend(payload.get('listing_ids', []))
                
                listings = self.db.get_listings_by_ids(listing_ids)
            
            logger.info(f"Analyzing {len(listings)} listings...")
            
            analyzed_count = 0
            high_score_count = 0
            
            for listing in listings:
                try:
                    # Calculate score
                    score = self.calculate_score(listing)
                    
                    # Update listing with score
                    self.db.update_listing_score(listing['id'], score)
                    
                    # Create event
                    self.db.create_event('listing_analyzed', {
                        'listing_id': listing['id'],
                        'score': score,
                        'url': listing.get('url')
                    })
                    
                    analyzed_count += 1
                    
                    # If score > 70, create decide mission
                    if score >= 70:
                        self.db.create_mission('decide', 'pending', {
                            'listing_id': listing['id'],
                            'score': score
                        })
                        high_score_count += 1
                        logger.info(f"🔥 High score listing ({score}): {listing.get('title', 'N/A')[:50]}...")
                    
                except Exception as e:
                    logger.error(f"Error analyzing listing {listing.get('id')}: {e}")
                    continue
            
            # Update mission statuses
            for mission in missions:
                self.db.update_mission_status(mission['id'], 'completed')
            
            # Log agent state
            self.db.log_agent_state('analyzer', 'completed', {
                'listings_analyzed': analyzed_count,
                'high_scores': high_score_count
            })
            
            logger.info(f"✅ Analyzer complete: {analyzed_count} analyzed, {high_score_count} high scores")
            
        except Exception as e:
            logger.error(f"❌ Analyzer failed: {e}")
            self.db.log_agent_state('analyzer', 'failed', {'error': str(e)})
            raise


if __name__ == '__main__':
    agent = AnalyzerAgent()
    asyncio.run(agent.run())
