#!/bin/bash
# Casa Hunt - Full Pipeline Runner
# Called by cron to run the complete property search pipeline
# Includes resource protection to avoid blocking the VPS

set -euo pipefail

PROJECT_DIR="/home/gabi/.openclaw/workspace/Projects/casa_hunt"
LOG_DIR="${PROJECT_DIR}/logs"
VENV="${PROJECT_DIR}/venv/bin"
TIMESTAMP=$(date "+%Y-%m-%d_%H-%M-%S")

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

echo "[${TIMESTAMP}] Starting full pipeline run..." >> "${LOG_DIR}/cron.log"

# Resource protection:
#   timeout 600  = kill after 10 minutes
#   nice -n 10   = lower CPU priority so VPS stays responsive
#   ulimit -v    = 512MB virtual memory cap
cd "${PROJECT_DIR}"
ulimit -v 524288 2>/dev/null || true
timeout 600 nice -n 10 "${VENV}/python" orchestrator.py --run-once \
    >> "${LOG_DIR}/pipeline_${TIMESTAMP}.log" 2>&1

EXIT_CODE=$?
echo "[$(date "+%Y-%m-%d_%H-%M-%S")] Pipeline completed (exit=${EXIT_CODE})." >> "${LOG_DIR}/cron.log"
