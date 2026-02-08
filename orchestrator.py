#!/usr/bin/env python3
"""
Casa Hunt - Agent Swarm Orchestrator
Coordinates all agents: Scout, Analyzer, Decision, Notifier
"""

import os
import sys

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from croniter import croniter

# Agent imports
from scout_agent import ScoutAgent, ScrapingConfig
from analyzer_agent import AnalyzerAgent
from decision_agent import DecisionAgent
from notifier_agent import NotifierAgent
from supabase_manager import SupabaseManager

# Configure logging to file
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'orchestrator.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('orchestrator')


class CasaHuntOrchestrator:
    """Main orchestrator that coordinates the agent swarm."""
    
    def __init__(self):
        self.supabase = SupabaseManager()
        self.agents = {
            'scout': ScoutAgent(),
            'analyzer': AnalyzerAgent(),
            'decision': DecisionAgent(),
            'notifier': NotifierAgent(),
        }
        self.running = False
        
    async def run_scout(self, on_batch_inserted=None):
        """Run the scout agent to scrape listings."""
        logger.info("🕵️  Running Scout Agent...")
        try:
            max_pages = int(os.getenv('MAX_PAGES', '10'))
            config = ScrapingConfig(max_pages=max_pages)
            await self.agents['scout'].run(config, on_batch_inserted=on_batch_inserted)
            logger.info("✅ Scout completed")
        except Exception as e:
            logger.error(f"❌ Scout failed: {e}")
    
    async def run_analyzer(self):
        """Run the analyzer to score listings."""
        logger.info("🧠 Running Analyzer Agent...")
        try:
            await self.agents['analyzer'].run()
            logger.info("✅ Analyzer completed")
        except Exception as e:
            logger.error(f"❌ Analyzer failed: {e}")
    
    async def run_decision(self):
        """Run the decision agent to approve/reject listings."""
        logger.info("⚖️  Running Decision Agent...")
        try:
            await self.agents['decision'].run()
            logger.info("✅ Decision completed")
        except Exception as e:
            logger.error(f"❌ Decision failed: {e}")
    
    async def run_notifier(self):
        """Run the notifier to send alerts."""
        logger.info("📱 Running Notifier Agent...")
        try:
            await self.agents['notifier'].run()
            logger.info("✅ Notifier completed")
        except Exception as e:
            logger.error(f"❌ Notifier failed: {e}")
    
    async def run_full_pipeline(self):
        """Run the complete pipeline with streaming notifications.

        As each batch of listings is inserted, immediately process them through
        analyze -> decide -> notify, so Telegram alerts arrive in real-time.
        """
        logger.info("\n" + "="*60)
        logger.info("🏠 CASA HUNT - FULL PIPELINE STARTING (streaming)")
        logger.info("="*60 + "\n")

        start_time = datetime.now(timezone.utc)
        stats = {'analyzed': 0, 'approved': 0, 'notified': 0}

        analyzer = self.agents['analyzer']
        decider = self.agents['decision']
        notifier = self.agents['notifier']

        async def process_batch(listing_ids):
            """Process a batch of newly inserted listings through the full pipeline."""
            logger.info(f"  📡 Streaming pipeline: processing {len(listing_ids)} listings...")

            # 1. Analyze: score each listing
            listings = self.supabase.get_listings_by_ids(listing_ids)
            high_score_ids = []
            for listing in listings:
                try:
                    score = analyzer.calculate_score(listing)
                    self.supabase.update_listing_score(listing['id'], score)
                    stats['analyzed'] += 1
                    if score >= 70:
                        high_score_ids.append(listing['id'])
                except Exception as e:
                    logger.error(f"  Analyze error for {listing.get('id')}: {e}")

            if not high_score_ids:
                return

            # 2. Decide: approve or reject high-score listings
            high_listings = self.supabase.get_listings_by_ids(high_score_ids)
            approved_ids = []
            decisions = {}
            for listing in high_listings:
                try:
                    decision, reason = decider.make_decision(listing)
                    self.supabase.update_listing_decision(listing['id'], decision, reason)
                    if decision == 'APPROVE':
                        approved_ids.append(listing['id'])
                        decisions[listing['id']] = reason
                        stats['approved'] += 1
                except Exception as e:
                    logger.error(f"  Decision error for {listing.get('id')}: {e}")

            if not approved_ids:
                return

            # 3. Notify: send Telegram for approved listings immediately
            approved_listings = self.supabase.get_listings_by_ids(approved_ids)
            for listing in approved_listings:
                try:
                    reason = decisions.get(listing['id'], '')
                    message = notifier.format_telegram_message(listing, reason)
                    result = await notifier.send_telegram(message)
                    if result:
                        self.supabase.mark_listing_notified(listing['id'])
                        stats['notified'] += 1
                    await asyncio.sleep(1)  # Telegram rate limit
                except Exception as e:
                    logger.error(f"  Notify error for {listing.get('id')}: {e}")

        # Step 1: Scout with streaming callback
        await self.run_scout(on_batch_inserted=process_batch)

        # Step 2: Catch any stragglers (unscored, undecided, unnotified)
        await self.run_analyzer()
        await self.run_decision()
        await self.run_notifier()

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        logger.info("\n" + "="*60)
        logger.info(f"✅ PIPELINE COMPLETE in {duration:.1f}s")
        logger.info(f"   Analyzed: {stats['analyzed']} | Approved: {stats['approved']} | Notified: {stats['notified']}")
        logger.info("="*60 + "\n")
    
    async def run_daemon(self):
        """Run as daemon with cron scheduling."""
        logger.info("🚀 Casa Hunt Orchestrator Daemon Starting...")
        self.running = True
        
        # Schedule: Daily at 10:00 AM for full pipeline
        # Every 10 minutes for mission processing
        
        while self.running:
            now = datetime.now(timezone.utc)
            
            # Check if it's time for full scrape (10:00 AM)
            if now.hour == 10 and now.minute < 10:
                await self.run_full_pipeline()
            else:
                # Process any pending missions
                await self.process_pending_missions()
            
            # Sleep for 10 minutes
            await asyncio.sleep(600)
    
    async def process_pending_missions(self):
        """Process any pending missions in the queue."""
        try:
            # Check for pending analyze missions
            await self.run_analyzer()
            
            # Check for pending decision missions
            await self.run_decision()
            
            # Check for pending notify missions
            await self.run_notifier()
            
        except Exception as e:
            logger.error(f"Error processing missions: {e}")
    
    def stop(self):
        """Stop the orchestrator."""
        logger.info("🛑 Stopping orchestrator...")
        self.running = False


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Casa Hunt Orchestrator')
    parser.add_argument('--run-once', action='store_true', help='Run pipeline once')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--scout-only', action='store_true', help='Run only scout')
    parser.add_argument('--status', action='store_true', help='Show agent status')
    
    args = parser.parse_args()
    
    orchestrator = CasaHuntOrchestrator()
    
    if args.run_once:
        await orchestrator.run_full_pipeline()
    elif args.daemon:
        await orchestrator.run_daemon()
    elif args.scout_only:
        await orchestrator.run_scout()
    elif args.status:
        print("📊 Agent Status: Not implemented yet")
    else:
        # Default: run once
        await orchestrator.run_full_pipeline()


if __name__ == '__main__':
    asyncio.run(main())
