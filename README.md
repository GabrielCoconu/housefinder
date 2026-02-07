# Casa Hunt - Agent Swarm Architecture

## Overview

Casa Hunt is a multi-agent system for automated house hunting in Bucharest. It scrapes listings, analyzes them with AI scoring, makes decisions, and sends notifications.

## Architecture (Inspired by Vox)

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                            │
│                    (Main Controller)                        │
└──────────────────┬──────────────────┬───────────────────────┘
                   │                  │
        ┌──────────▼────────┐  ┌─────▼──────┐
        │    CRON (10:00)   │  │  Events    │
        └──────────┬────────┘  └─────┬──────┘
                   │                  │
┌──────────────────▼──────────────────▼───────────────────────┐
│                      AGENT SWARM                            │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│   SCOUT     │  ANALYZER   │  DECISION   │   NOTIFIER        │
│  (Scraper)  │  (Scoring)  │ (Approver)  │  (Alerts)         │
└──────┬──────┴──────┬──────┴──────┬──────┴────────┬──────────┘
       │             │             │               │
       ▼             ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                      SUPABASE DATABASE                      │
│  ┌────────────┬────────────┬────────────┬─────────────────┐ │
│  │ listings   │  missions  │   events   │  agent_state    │ │
│  └────────────┴────────────┴────────────┴─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Agents

### 1. Scout Agent (`scout_agent.py`)
- **Purpose:** Scrapes Imobiliare.ro and Storia.ro
- **Schedule:** Daily at 10:00 AM
- **Output:** Saves listings to Supabase, creates `listings_scraped` event
- **Triggers:** Creates `analyze` missions for new listings

### 2. Analyzer Agent (`analyzer_agent.py`)
- **Purpose:** Scores listings based on multiple criteria
- **Schedule:** Every 10 minutes (checks for pending missions)
- **Scoring Algorithm:**
  - Price per mp: 0-40 points (lower = better)
  - Metro proximity: 30 points
  - Location quality: 20 points
  - Under budget: 10 points
- **Output:** Updates listing score, creates `listing_analyzed` event
- **Triggers:** If score > 70, creates `decide` mission

### 3. Decision Agent (`decision_agent.py`)
- **Purpose:** Approves or rejects listings based on hard criteria
- **Schedule:** Every 10 minutes
- **Criteria:**
  - Budget: ≤ 200,000 EUR
  - Location: Bucuresti or Ilfov
  - Type: Casa/Vila
- **Output:** Creates `listing_decided` event
- **Triggers:** If APPROVED, creates `notify` mission

### 4. Notifier Agent (`notifier_agent.py`)
- **Purpose:** Sends alerts via Telegram and ClickUp
- **Schedule:** Every 10 minutes
- **Output:** Telegram message + ClickUp task
- **Format:** Title, price, location, score, link

## Database Schema

### listings
```sql
- id (uuid, primary key)
- source (text)
- external_id (text)
- url (text, unique)
- title (text)
- price_raw (text)
- price_eur (int)
- location (text)
- surface_mp (int)
- rooms (int)
- features_raw (text)
- metro_nearby (boolean)
- score (int)  -- Added by Analyzer
- decision (text)  -- Added by Decision
- scraped_at (timestamp)
- created_at (timestamp)
```

### missions
```sql
- id (uuid, primary key)
- type (text: scrape/analyze/decide/notify)
- status (text: pending/processing/completed/failed)
- payload (jsonb)
- created_at (timestamp)
- updated_at (timestamp)
- completed_at (timestamp)
```

### events
```sql
- id (uuid, primary key)
- type (text)
- payload (jsonb)
- processed (boolean)
- created_at (timestamp)
- processed_at (timestamp)
```

### agent_state
```sql
- id (uuid, primary key)
- agent_name (text)
- agent_version (text)
- state (text)
- details (jsonb)
- created_at (timestamp)
```

## Installation

### 1. Install Dependencies

```bash
cd Projects/casa_hunt
pip install -r requirements.txt
```

### 2. Setup Supabase

1. Create project at [supabase.com](https://supabase.com)
2. Run SQL schema from `supabase/schema.sql`
3. Copy `.env.example` to `.env` and fill credentials

### 3. Configure Environment

```bash
# .env file
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

## Usage

### Run Once (Manual)

```bash
# Full pipeline
python orchestrator.py --run-once

# Only scout
python orchestrator.py --scout-only
```

### Run as Daemon (Production)

```bash
# Start daemon
python orchestrator.py --daemon

# Stop daemon
# (Ctrl+C or kill process)
```

### Setup Cron (Alternative)

```bash
# Add to crontab
crontab -e

# Daily at 10:00 AM
0 10 * * * cd /home/gabi/.openclaw/workspace/Projects/casa_hunt && python3 orchestrator.py --run-once >> logs/cron.log 2>&1
```

## File Structure

```
Projects/casa_hunt/
├── orchestrator.py      # Main controller
├── scout_agent.py       # Scraper
├── analyzer_agent.py    # AI scoring
├── decision_agent.py    # Approval logic
├── notifier_agent.py    # Telegram + ClickUp
├── supabase_manager.py  # Database wrapper
├── requirements.txt     # Dependencies
├── .env                 # Environment variables
├── supabase/
│   ├── schema.sql       # Database schema
│   └── SETUP.md         # Setup instructions
├── src/                 # Legacy scrapers
│   └── casa_playwright.py
└── docs/
    └── README.md        # This file
```

## Monitoring

Check agent status:
```bash
python orchestrator.py --status
```

View logs:
```bash
tail -f logs/scout.log
tail -f logs/analyzer.log
tail -f logs/orchestrator.log
```

## Troubleshooting

### Agent not running
- Check Supabase credentials
- Verify network connectivity
- Review logs in `logs/` directory

### No listings found
- Check scraper selectors (sites may change)
- Verify filters (price, location)
- Try running scout manually

### Duplicate listings
- Supabase `url` column has unique constraint
- Scout checks existing URLs before insert

## Credits

Architecture inspired by [Vox Agent World](https://x.com/Voxyz_ai) - 6 AI agents autonomously operating with OpenClaw + Supabase + Next.js.
