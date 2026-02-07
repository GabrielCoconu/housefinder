#!/usr/bin/env python3
"""Quick test to send a Telegram notification."""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '8493404456')

def send_test_message():
    """Send a test Telegram message."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        return False
    
    message = f"""
🏠 <b>CASA HUNT TEST</b> 🐝

✅ Pipeline funcționează!

📊 Rezultate test:
• Scraped: 8 listings
• Analyzed: 3 listings  
• Approved: 0 (toate sub 70 puncte)

📍 Listinguri găsite:
1. Vilă Sector 6 - 165.000€ (47/100)
2. Casa Chitilei - 145.000€ (25/100)
3. Casa Rahova - 172.500€ (37/100)

🔗 <a href="https://www.storia.ro/ro/rezultate/vanzare/casa/bucuresti?priceMax=200000">Vezi toate pe Storia</a>

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}

<i>Scraper JSON funcționează! 🚀</i>
"""
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        if result.get('ok'):
            print(f"✅ Telegram message sent! message_id={result['result']['message_id']}")
            return True
        else:
            print(f"❌ Telegram API error: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to send Telegram: {e}")
        return False

if __name__ == '__main__':
    print("📱 Sending test Telegram message...")
    print("="*60)
    success = send_test_message()
    print("="*60)
    if success:
        print("🎉 Message sent successfully!")
    else:
        print("❌ Failed to send message")
