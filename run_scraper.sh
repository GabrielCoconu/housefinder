#!/bin/bash
# Casa Hunt - Scraper Runner
# Called by cron to run the daily property search

set -euo pipefail

PROJECT_DIR="/home/gabi/.openclaw/workspace/Projects/casa_hunt"
LOG_DIR="${PROJECT_DIR}/logs"
VENV="${PROJECT_DIR}/venv/bin"
TIMESTAMP=$(date "+%Y-%m-%d_%H-%M-%S")

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

echo "[${TIMESTAMP}] Starting scraper run..." >> "${LOG_DIR}/cron.log"

# Run the scout agent
cd "${PROJECT_DIR}"
"${VENV}/python" scout_agent.py >> "${LOG_DIR}/scraper_${TIMESTAMP}.log" 2>&1

echo "[$(date "+%Y-%m-%d_%H-%M-%S")] Scraper run completed." >> "${LOG_DIR}/cron.log"
