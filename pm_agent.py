#!/usr/bin/env python3
"""
Casa Hunt - PM Agent (Project Manager)
Coordinates the agent swarm and manages tasks/bugs
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from supabase_manager import SupabaseManager

# Setup logging
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'pm_agent.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('pm_agent')


class PMAgent:
    """Project Manager - coordinates the agent swarm."""
    
    def __init__(self):
        self.db = SupabaseManager()
        self.backlog = []
        self.bugs = []
        
    async def run_daily_standup(self):
        """Daily check of all agents status."""
        logger.info("="*60)
        logger.info("📋 PM AGENT - DAILY STANDUP")
        logger.info("="*60)
        
        # Check agent states
        states = self.db.get_agent_states(limit=20)
        
        agent_status = {}
        for state in states:
            agent = state['agent_name']
            if agent not in agent_status:
                agent_status[agent] = state
        
        logger.info(f"\nAgent Status:")
        for agent, state in agent_status.items():
            status_emoji = "✅" if state['state'] == 'completed' else "❌" if state['state'] == 'failed' else "⏳"
            logger.info(f"  {status_emoji} {agent}: {state['state']}")
        
        # Check for failed agents
        failed = [a for a, s in agent_status.items() if s['state'] == 'failed']
        if failed:
            logger.error(f"\n🚨 FAILED AGENTS: {', '.join(failed)}")
            await self.create_bug_report(failed)
        
        # Check pending missions
        pending = self.db.get_pending_missions('analyze') + \
                  self.db.get_pending_missions('decide') + \
                  self.db.get_pending_missions('notify')
        
        if pending:
            logger.info(f"\n⏳ Pending missions: {len(pending)}")
        
        return agent_status
    
    async def create_bug_report(self, failed_agents: List[str]):
        """Create bug report for failed agents."""
        for agent in failed_agents:
            bug = {
                'type': 'bug',
                'severity': 'high',
                'title': f'{agent} agent failed',
                'description': f'Agent {agent} reported failed state',
                'status': 'open',
                'assigned_to': 'developer',
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            self.bugs.append(bug)
            logger.info(f"🐛 Bug created: {bug['title']}")
    
    async def assign_task(self, task_type: str, payload: Dict):
        """Assign task to appropriate agent."""
        logger.info(f"📋 Assigning {task_type} task...")
        
        mission_id = self.db.create_mission(task_type, 'pending', payload)
        logger.info(f"✅ Task assigned: {mission_id}")
        return mission_id
    
    async def review_qa_report(self, report: Dict):
        """Review QA report and create action items."""
        logger.info("="*60)
        logger.info("📊 REVIEWING QA REPORT")
        logger.info("="*60)
        
        issues = report.get('issues', [])
        if not issues:
            logger.info("✅ No issues found by QA")
            return
        
        for issue in issues:
            logger.warning(f"🐛 Issue: {issue['type']} - {issue['description']}")
            
            if issue['severity'] == 'critical':
                await self.assign_task('fix_critical', issue)
            elif issue['severity'] == 'high':
                await self.assign_task('fix_bug', issue)
            else:
                await self.assign_task('improve', issue)
    
    async def run(self):
        """Main PM loop."""
        logger.info("🎯 PM Agent starting...")
        
        # Daily standup
        status = await self.run_daily_standup()
        
        # Check if QA has reported issues
        # (In real implementation, this would check a queue)
        
        logger.info("\n✅ PM standup complete")
        return status


if __name__ == '__main__':
    agent = PMAgent()
    asyncio.run(agent.run())
