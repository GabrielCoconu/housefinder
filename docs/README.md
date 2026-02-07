# Casa Hunt - Project Documentation

## Overview
Automated house hunting system for Bucharest real estate. Scrapes Imobiliare.ro and Storia.ro for houses under 200k EUR with metro access.

## Project Structure

```
Projects/casa_hunt/
├── src/                    # Source code
│   ├── casa_hunt.py       # Main orchestrator
│   ├── imobiliare_scraper.py
│   ├── storia_scraper.py
│   └── scraper_utils.py
├── docs/                   # Documentation
│   ├── PRD.md             # Product Requirements
│   ├── README.md          # This file
│   └── ARCHITECTURE.md    # System design
├── tests/                  # Test suite
├── results/                # Scraping output (JSON)
├── logs/                   # Execution logs
└── config/                 # Configuration files
```

## Quick Start

```bash
cd Projects/casa_hunt

# Install dependencies
pip install -r requirements.txt

# Run scraper
python3 src/casa_hunt.py -o results -p 3

# Check results
cat results/listings_*.json
```

## Configuration

Edit budget, pages, or other settings in `src/casa_hunt.py` or pass arguments:

```bash
python3 src/casa_hunt.py --budget 180000 --max-pages 5
```

## Cron Job

Runs daily at 10:00 Bucharest time via existing cron setup.

## Team (Swarm Agents)

- **PM**: Requirements & acceptance criteria
- **Dev 1**: Imobiliare.ro scraper
- **Dev 2**: Storia.ro scraper  
- **Dev 3**: Utils & parsers
- **Dev 4**: Orchestrator
- **QA**: Testing & validation
