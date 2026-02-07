#!/usr/bin/env python3
"""
Casa Hunt - QA Agent
Tests the system and reports bugs to PM Agent
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional
from urllib.parse import urlparse
from supabase_manager import SupabaseManager

# Setup logging
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'qa_agent.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('qa_agent')


class QAAgent:
    """Quality Assurance - tests the system and finds bugs."""
    
    def __init__(self):
        self.db = SupabaseManager()
        self.issues = []
        
    def test_url_validity(self, url: str) -> tuple[bool, str]:
        """Test if URL is valid and not a test URL."""
        if not url:
            return False, "URL is empty"
        
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL format"
        
        # Check for test URLs
        test_domains = ['test.com', 'example.com', 'localhost', 'casa-1', 'casa-2']
        if any(td in url for td in test_domains):
            return False, f"Test URL detected: {url}"
        
        return True, "OK"
    
    def test_price_validity(self, price: Optional[int], price_raw: str) -> tuple[bool, str]:
        """Test if price is reasonable."""
        if price is None:
            return False, "Price is None"
        
        if price < 10000:
            return False, f"Price too low: {price}€"
        
        if price > 1000000:
            return False, f"Price too high: {price}€"
        
        # Check if raw price matches parsed price
        if price_raw:
            digits_in_raw = re.sub(r'[^\d]', '', price_raw)
            if digits_in_raw and int(digits_in_raw) != price:
                return False, f"Price mismatch: raw={price_raw}, parsed={price}"
        
        return True, "OK"
    
    def test_location_validity(self, location: str) -> tuple[bool, str]:
        """Test if location is valid."""
        if not location or location in ['N/A', '', 'Bucuresti']:
            return False, f"Invalid location: {location}"
        
        # Should contain specific area, not just city
        if location.lower() == 'bucuresti':
            return False, "Location too generic (just 'Bucuresti')"
        
        return True, "OK"
    
    def test_data_completeness(self, listing: Dict) -> tuple[bool, List[str]]:
        """Test if all required fields are present."""
        required = ['url', 'title', 'price_eur', 'location', 'scraped_at']
        missing = [f for f in required if not listing.get(f)]
        
        if missing:
            return False, missing
        
        return True, []
    
    async def test_scout_output(self) -> List[Dict]:
        """Test Scout Agent output quality."""
        logger.info("🧪 Testing Scout Agent output...")
        
        issues = []
        
        # Get recent listings
        listings = self.db.client.table('listings') \
            .select('*') \
            .order('created_at', desc=True) \
            .limit(10) \
            .execute()
        
        for listing in listings.data:
            listing_id = listing['id']
            
            # Test URL
            valid, msg = self.test_url_validity(listing.get('url', ''))
            if not valid:
                issues.append({
                    'type': 'invalid_url',
                    'severity': 'critical',
                    'listing_id': listing_id,
                    'description': msg,
                    'agent': 'scout'
                })
            
            # Test price
            valid, msg = self.test_price_validity(
                listing.get('price_eur'),
                listing.get('price_raw', '')
            )
            if not valid:
                issues.append({
                    'type': 'invalid_price',
                    'severity': 'high',
                    'listing_id': listing_id,
                    'description': msg,
                    'agent': 'scout'
                })
            
            # Test location
            valid, msg = self.test_location_validity(listing.get('location', ''))
            if not valid:
                issues.append({
                    'type': 'invalid_location',
                    'severity': 'medium',
                    'listing_id': listing_id,
                    'description': msg,
                    'agent': 'scout'
                })
            
            # Test completeness
            valid, missing = self.test_data_completeness(listing)
            if not valid:
                issues.append({
                    'type': 'incomplete_data',
                    'severity': 'high',
                    'listing_id': listing_id,
                    'description': f"Missing fields: {', '.join(missing)}",
                    'agent': 'scout'
                })
        
        logger.info(f"  Found {len(issues)} issues in Scout output")
        return issues
    
    async def test_analyzer_logic(self) -> List[Dict]:
        """Test Analyzer Agent scoring logic."""
        logger.info("🧪 Testing Analyzer Agent logic...")
        
        issues = []
        
        # Get listings with scores
        listings = self.db.client.table('listings') \
            .select('*') \
            .not_.is_('score', 'null') \
            .limit(10) \
            .execute()
        
        for listing in listings.data:
            score = listing.get('score')
            price = listing.get('price_eur')
            
            # Test score range
            if score < 0 or score > 100:
                issues.append({
                    'type': 'invalid_score',
                    'severity': 'critical',
                    'listing_id': listing['id'],
                    'description': f"Score out of range: {score}",
                    'agent': 'analyzer'
                })
            
            # Test score consistency with price
            if price and price > 200000 and score > 70:
                issues.append({
                    'type': 'suspicious_score',
                    'severity': 'medium',
                    'listing_id': listing['id'],
                    'description': f"High score ({score}) for expensive house ({price}€)",
                    'agent': 'analyzer'
                })
        
        logger.info(f"  Found {len(issues)} issues in Analyzer logic")
        return issues
    
    async def test_notifier_output(self) -> List[Dict]:
        """Test Notifier Agent output."""
        logger.info("🧪 Testing Notifier Agent output...")
        
        issues = []
        
        # Check for approved listings that weren't notified
        approved = self.db.client.table('listings') \
            .select('*') \
            .eq('decision', 'APPROVE') \
            .is_('notified_at', 'null') \
            .execute()
        
        if approved.data:
            issues.append({
                'type': 'missing_notification',
                'severity': 'high',
                'description': f"{len(approved.data)} approved listings not notified",
                'agent': 'notifier'
            })
        
        # Check for test URLs in notifications
        for listing in approved.data:
            valid, msg = self.test_url_validity(listing.get('url', ''))
            if not valid:
                issues.append({
                    'type': 'test_url_notified',
                    'severity': 'critical',
                    'listing_id': listing['id'],
                    'description': f"Test URL would be sent to user: {msg}",
                    'agent': 'notifier'
                })
        
        logger.info(f"  Found {len(issues)} issues in Notifier output")
        return issues
    
    async def run_full_test_suite(self) -> Dict:
        """Run complete test suite."""
        logger.info("="*60)
        logger.info("🧪 QA AGENT - FULL TEST SUITE")
        logger.info("="*60)
        
        all_issues = []
        
        # Test each component
        all_issues.extend(await self.test_scout_output())
        all_issues.extend(await self.test_analyzer_logic())
        all_issues.extend(await self.test_notifier_output())
        
        # Create report
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total_issues': len(all_issues),
            'critical': len([i for i in all_issues if i['severity'] == 'critical']),
            'high': len([i for i in all_issues if i['severity'] == 'high']),
            'medium': len([i for i in all_issues if i['severity'] == 'medium']),
            'issues': all_issues
        }
        
        # Log report
        logger.info("\n" + "="*60)
        logger.info("📊 QA REPORT")
        logger.info("="*60)
        logger.info(f"Total Issues: {report['total_issues']}")
        logger.info(f"  Critical: {report['critical']} 🚨")
        logger.info(f"  High: {report['high']} ⚠️")
        logger.info(f"  Medium: {report['medium']} ℹ️")
        
        if all_issues:
            logger.info("\nIssues found:")
            for issue in all_issues:
                emoji = "🚨" if issue['severity'] == 'critical' else "⚠️" if issue['severity'] == 'high' else "ℹ️"
                logger.info(f"  {emoji} [{issue['agent']}] {issue['type']}: {issue['description']}")
        
        # Create event for PM Agent
        self.db.create_event('qa_report', report)
        logger.info("\n✅ QA report sent to PM Agent")
        
        return report
    
    async def run(self):
        """Main QA loop."""
        logger.info("🎯 QA Agent starting...")
        report = await self.run_full_test_suite()
        return report


if __name__ == '__main__':
    agent = QAAgent()
    asyncio.run(agent.run())
