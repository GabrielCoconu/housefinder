#!/usr/bin/env python3
"""
Casa Hunt - Decision Agent
Approves or rejects listings based on hard criteria
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List
from supabase_manager import SupabaseManager

# Setup logging to file
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'decision.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('decision_agent')


class DecisionAgent:
    """Makes approve/reject decisions on high-scoring listings."""
    
    def __init__(self):
        self.db = SupabaseManager()
        self.min_score = 70
        self.max_price = 200000
        self.required_keywords = ['casa', 'vila', 'duplex']
        self.location_keywords = ['bucuresti', 'ilfov']
    
    def check_budget(self, price_eur: int) -> bool:
        """Check if price is within budget."""
        return price_eur is not None and price_eur <= self.max_price
    
    def check_location(self, location: str) -> bool:
        """Check if location is in target area."""
        location_lower = location.lower()
        return any(kw in location_lower for kw in self.location_keywords)
    
    def check_property_type(self, title: str, features: str = "") -> bool:
        """Check if it's a house/villa (not apartment)."""
        text = f"{title} {features}".lower()
        
        # Must contain house keywords
        is_house = any(kw in text for kw in self.required_keywords)
        
        # Must NOT contain apartment keywords
        apt_keywords = ['apartament', 'garsoniera', 'studio']
        is_apartment = any(kw in text for kw in apt_keywords)
        
        return is_house and not is_apartment
    
    def make_decision(self, listing: Dict) -> tuple[str, str]:
        """
        Make approve/reject decision.
        Returns: (decision, reason)
        """
        price_eur = listing.get('price_eur')
        location = listing.get('location', '')
        title = listing.get('title', '')
        features = listing.get('features_raw', '')
        score = listing.get('score', 0)
        
        checks = []
        
        # Check 1: Score
        if score < self.min_score:
            return 'REJECT', f'Score {score} below threshold {self.min_score}'
        checks.append(f'Score: {score} ✓')
        
        # Check 2: Budget
        if not self.check_budget(price_eur):
            return 'REJECT', f'Price {price_eur}€ exceeds budget {self.max_price}€'
        checks.append(f'Budget: {price_eur}€ ✓')
        
        # Check 3: Location
        if not self.check_location(location):
            return 'REJECT', f'Location "{location}" not in target area'
        checks.append(f'Location: {location} ✓')
        
        # Check 4: Property Type
        if not self.check_property_type(title, features):
            return 'REJECT', f'Property type not suitable (looking for casa/vila)'
        checks.append(f'Type: House/Villa ✓')
        
        # All checks passed
        return 'APPROVE', ' | '.join(checks)
    
    async def run(self):
        """Main agent loop."""
        logger.info("⚖️  Decision Agent starting...")
        
        try:
            # Get pending decide missions
            missions = self.db.get_pending_missions('decide')
            
            if not missions:
                logger.info("No pending decide missions")
                # Also check for high-scored unprocessed listings
                listings = self.db.get_high_score_listings(self.min_score, undecided_only=True)
                if not listings:
                    logger.info("No listings awaiting decision")
                    return
            else:
                # Extract listing IDs from missions
                listing_ids = []
                for mission in missions:
                    payload = mission.get('payload', {})
                    listing_ids.append(payload.get('listing_id'))
                
                listings = self.db.get_listings_by_ids(listing_ids)
            
            logger.info(f"Processing {len(listings)} listings for decision...")
            
            approved_count = 0
            rejected_count = 0
            
            for listing in listings:
                try:
                    decision, reason = self.make_decision(listing)
                    
                    # Update listing with decision
                    self.db.update_listing_decision(listing['id'], decision, reason)
                    
                    # Create event
                    self.db.create_event('listing_decided', {
                        'listing_id': listing['id'],
                        'decision': decision,
                        'reason': reason,
                        'score': listing.get('score'),
                        'price': listing.get('price_eur')
                    })
                    
                    if decision == 'APPROVE':
                        approved_count += 1
                        # Create notify mission
                        self.db.create_mission('notify', 'pending', {
                            'listing_id': listing['id'],
                            'decision': decision,
                            'reason': reason
                        })
                        logger.info(f"✅ APPROVED: {listing.get('title', 'N/A')[:50]}...")
                    else:
                        rejected_count += 1
                        logger.info(f"❌ REJECTED: {listing.get('title', 'N/A')[:50]}... ({reason})")
                    
                except Exception as e:
                    logger.error(f"Error deciding on listing {listing.get('id')}: {e}")
                    continue
            
            # Update mission statuses
            for mission in missions:
                self.db.update_mission_status(mission['id'], 'completed')
            
            # Log agent state
            self.db.log_agent_state('decision', 'completed', {
                'approved': approved_count,
                'rejected': rejected_count
            })
            
            logger.info(f"✅ Decision complete: {approved_count} approved, {rejected_count} rejected")
            
        except Exception as e:
            logger.error(f"❌ Decision agent failed: {e}")
            self.db.log_agent_state('decision', 'failed', {'error': str(e)})
            raise


if __name__ == '__main__':
    agent = DecisionAgent()
    asyncio.run(agent.run())
