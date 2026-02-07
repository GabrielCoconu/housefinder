#!/usr/bin/env python3
"""
Casa Hunt - Notifier Agent
Sends alerts via Telegram and creates ClickUp tasks
"""

import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from supabase_manager import SupabaseManager

# Telegram
import requests

# ClickUp
import subprocess
import json

# Setup logging to file
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'notifier.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('notifier_agent')


class NotifierAgent:
    """Sends notifications for approved listings."""
    
    def __init__(self):
        self.db = SupabaseManager()
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '8493404456')  # Default to Gabi
        self.clickup_token_path = os.path.expanduser('~/.config/clickup/token')
        self.clickup_list_id = None  # Will be auto-discovered
    
    def get_clickup_token(self) -> Optional[str]:
        """Read ClickUp token from file."""
        try:
            with open(self.clickup_token_path, 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error(f"ClickUp token not found at {self.clickup_token_path}")
            return None
    
    def get_or_create_clickup_list(self) -> Optional[str]:
        """Get or create 'Casa Hunt' list in ClickUp."""
        if self.clickup_list_id:
            return self.clickup_list_id
        
        token = self.get_clickup_token()
        if not token:
            return None
        
        try:
            # First, get spaces
            result = subprocess.run(
                ['clickup', 'spaces'],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to get ClickUp spaces: {result.stderr}")
                return None
            
            # Try to find "Personal" space and "Casa Hunt" list
            result = subprocess.run(
                ['clickup', 'lists', '--space', 'Personal'],
                capture_output=True,
                text=True
            )
            
            if 'casa hunt' in result.stdout.lower():
                # Extract list ID (this is simplified - real implementation would parse JSON)
                logger.info("Found Casa Hunt list in ClickUp")
                # For now, return a placeholder - in production would parse properly
                return "casa_hunt_list_id"
            
            # Create the list if not found
            logger.info("Creating Casa Hunt list in ClickUp...")
            # Would use: clickup list create --name "Casa Hunt" --space "Personal"
            
        except Exception as e:
            logger.error(f"ClickUp error: {e}")
            return None
    
    def format_telegram_message(self, listing: Dict, decision_reason: str) -> str:
        """Format a Telegram message for a listing."""
        title = listing.get('title', 'N/A')
        price = listing.get('price_eur', 'N/A')
        location = listing.get('location', 'N/A')
        surface = listing.get('surface_mp')
        score = listing.get('score', 0)
        url = listing.get('url', '')
        
        # Score emoji
        if score >= 85:
            score_emoji = '🔥'
        elif score >= 70:
            score_emoji = '⭐'
        else:
            score_emoji = '👍'
        
        # Price formatting
        if isinstance(price, int):
            price_str = f"{price:,}€".replace(',', '.')
        else:
            price_str = str(price)
        
        # Surface formatting
        surface_str = f"{surface}mp" if surface else "Surface N/A"
        
        message = f"""
🏠 <b>CASA HUNT ALERT</b> {score_emoji}

<b>{title}</b>

💰 <b>Price:</b> {price_str}
📍 <b>Location:</b> {location}
📐 <b>Surface:</b> {surface_str}
📊 <b>Score:</b> {score}/100

✅ <b>Approved:</b> {decision_reason}

🔗 <a href="{url}">View Listing</a>

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        return message.strip()
    
    async def send_telegram(self, message: str) -> Optional[str]:
        """Send message via Telegram Bot API."""
        if not self.telegram_token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return None
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if result.get('ok'):
                message_id = result['result']['message_id']
                logger.info(f"✅ Telegram sent: message_id={message_id}")
                return str(message_id)
            else:
                logger.error(f"Telegram API error: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to send Telegram: {e}")
            return None
    
    async def create_clickup_task(self, listing: Dict) -> Optional[str]:
        """Create a task in ClickUp."""
        list_id = self.get_or_create_clickup_list()
        if not list_id:
            logger.warning("Skipping ClickUp - no list available")
            return None
        
        try:
            title = f"🏠 {listing.get('title', 'Casa')[:50]}"
            price = listing.get('price_eur', 'N/A')
            url = listing.get('url', '')
            score = listing.get('score', 0)
            
            description = f"""
Price: {price}€
Score: {score}/100
URL: {url}

Review and contact if interested.
"""
            
            # Priority based on score
            if score >= 85:
                priority = "urgent"
            elif score >= 75:
                priority = "high"
            else:
                priority = "normal"
            
            # Use clickup CLI
            result = subprocess.run(
                [
                    'clickup', 'add', list_id, title,
                    '--description', description,
                    '--priority', priority
                ],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"✅ ClickUp task created: {title}")
                return "task_id_placeholder"  # Would extract from output
            else:
                logger.error(f"ClickUp error: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create ClickUp task: {e}")
            return None
    
    async def run(self):
        """Main agent loop."""
        logger.info("📱 Notifier Agent starting...")
        
        try:
            # Get pending notify missions
            missions = self.db.get_pending_missions('notify')
            
            if not missions:
                logger.info("No pending notify missions")
                # Also check for approved unnotified listings
                listings = self.db.get_approved_unnotified_listings()
                if not listings:
                    logger.info("No listings to notify")
                    return
            else:
                # Extract listing IDs from missions
                listing_ids = []
                for mission in missions:
                    payload = mission.get('payload', {})
                    listing_ids.append(payload.get('listing_id'))
                
                listings = self.db.get_listings_by_ids(listing_ids)
            
            logger.info(f"Notifying for {len(listings)} approved listings...")
            
            notified_count = 0
            
            for listing in listings:
                try:
                    # Get decision reason
                    decision = listing.get('decision', 'APPROVE')
                    reason = listing.get('decision_reason', 'High score')
                    
                    if decision != 'APPROVE':
                        continue
                    
                    # Format and send Telegram
                    message = self.format_telegram_message(listing, reason)
                    telegram_id = await self.send_telegram(message)
                    
                    # Create ClickUp task
                    clickup_id = await self.create_clickup_task(listing)
                    
                    # Mark as notified
                    self.db.mark_listing_notified(listing['id'])
                    
                    # Create event
                    self.db.create_event('notification_sent', {
                        'listing_id': listing['id'],
                        'telegram_message_id': telegram_id,
                        'clickup_task_id': clickup_id
                    })
                    
                    notified_count += 1
                    
                    # Rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error notifying for listing {listing.get('id')}: {e}")
                    continue
            
            # Update mission statuses
            for mission in missions:
                self.db.update_mission_status(mission['id'], 'completed')
            
            # Log agent state
            self.db.log_agent_state('notifier', 'completed', {
                'notified': notified_count
            })
            
            logger.info(f"✅ Notifier complete: {notified_count} notifications sent")
            
        except Exception as e:
            logger.error(f"❌ Notifier failed: {e}")
            self.db.log_agent_state('notifier', 'failed', {'error': str(e)})
            raise


if __name__ == '__main__':
    agent = NotifierAgent()
    asyncio.run(agent.run())
