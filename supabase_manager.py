#!/usr/bin/env python3
"""
Casa Hunt - Supabase Manager
Wrapper for Supabase database operations
"""

import os
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

try:
    from supabase import create_client, Client
except ImportError:
    raise ImportError("supabase-py not installed. Run: pip install supabase")

logger = logging.getLogger('supabase_manager')


class SupabaseManager:
    """Manages all Supabase database operations."""
    
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL', 'https://your-project.supabase.co')
        self.key = os.getenv('SUPABASE_KEY', 'your-key')
        self.client: Client = create_client(self.url, self.key)
        logger.info(f"Connected to Supabase: {self.url[:30]}...")
    
    # =========================================================================
    # Listings Operations
    # =========================================================================
    
    def get_existing_urls(self, urls: List[str]) -> set:
        """Check which URLs already exist in the database."""
        if not urls:
            return set()
        
        existing = set()
        batch_size = 100
        
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            result = self.client.table("listings") \
                .select("url") \
                .in_("url", batch) \
                .execute()
            
            if result.data:
                existing.update(item["url"] for item in result.data)
        
        return existing
    
    def insert_listings(self, listings: List[Dict]) -> List[str]:
        """Insert listings, skipping duplicates. Returns inserted IDs."""
        if not listings:
            return []
        
        result = self.client.table("listings").upsert(
            listings,
            on_conflict="url"
        ).execute()
        
        return [item["id"] for item in result.data] if result.data else []
    
    def get_listings_by_ids(self, ids: List[str]) -> List[Dict]:
        """Get listings by their IDs."""
        if not ids:
            return []
        
        result = self.client.table("listings") \
            .select("*") \
            .in_("id", ids) \
            .execute()
        
        return result.data or []
    
    def get_unscored_listings(self) -> List[Dict]:
        """Get listings without a score."""
        result = self.client.table("listings") \
            .select("*") \
            .is_("score", "null") \
            .execute()
        
        return result.data or []
    
    def get_high_score_listings(self, min_score: int = 70, undecided_only: bool = True) -> List[Dict]:
        """Get listings with high scores."""
        query = self.client.table("listings") \
            .select("*") \
            .gte("score", min_score)
        
        if undecided_only:
            query = query.is_("decision", "null")
        
        result = query.execute()
        return result.data or []
    
    def get_approved_unnotified_listings(self) -> List[Dict]:
        """Get approved listings that haven't been notified."""
        result = self.client.table("listings") \
            .select("*") \
            .eq("decision", "APPROVE") \
            .is_("notified_at", "null") \
            .execute()
        
        return result.data or []
    
    def update_listing_score(self, listing_id: str, score: int):
        """Update listing with calculated score."""
        self.client.table("listings") \
            .update({
                "score": score,
                "analyzed_at": datetime.now(timezone.utc).isoformat()
            }) \
            .eq("id", listing_id) \
            .execute()
    
    def update_listing_decision(self, listing_id: str, decision: str, reason: str):
        """Update listing with decision."""
        self.client.table("listings") \
            .update({
                "decision": decision,
                "decision_reason": reason,
                "decided_at": datetime.now(timezone.utc).isoformat()
            }) \
            .eq("id", listing_id) \
            .execute()
    
    def mark_listing_notified(self, listing_id: str):
        """Mark listing as notified."""
        self.client.table("listings") \
            .update({
                "notified_at": datetime.now(timezone.utc).isoformat()
            }) \
            .eq("id", listing_id) \
            .execute()
    
    # =========================================================================
    # Missions Operations
    # =========================================================================
    
    def get_pending_missions(self, mission_type: str) -> List[Dict]:
        """Get pending missions of a specific type."""
        result = self.client.table("missions") \
            .select("*") \
            .eq("type", mission_type) \
            .eq("status", "pending") \
            .execute()
        
        return result.data or []
    
    def create_mission(self, mission_type: str, status: str, payload: Dict) -> Optional[str]:
        """Create a new mission."""
        data = {
            "type": mission_type,
            "status": status,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        result = self.client.table("missions").insert(data).execute()
        
        if result.data:
            return result.data[0].get("id")
        return None
    
    def update_mission_status(self, mission_id: str, status: str):
        """Update mission status."""
        self.client.table("missions") \
            .update({
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat() if status == "completed" else None
            }) \
            .eq("id", mission_id) \
            .execute()
    
    # =========================================================================
    # Events Operations
    # =========================================================================
    
    def create_event(self, event_type: str, payload: Dict) -> Optional[str]:
        """Create an event."""
        data = {
            "type": event_type,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processed": False
        }
        
        result = self.client.table("events").insert(data).execute()
        
        if result.data:
            return result.data[0].get("id")
        return None
    
    # =========================================================================
    # Agent State Operations
    # =========================================================================
    
    def log_agent_state(self, agent_name: str, state: str, details: Dict = None):
        """Log agent state."""
        data = {
            "agent_name": agent_name,
            "state": state,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        self.client.table("agent_state").insert(data).execute()
    
    def get_agent_states(self, agent_name: str = None, limit: int = 10) -> List[Dict]:
        """Get recent agent states."""
        query = self.client.table("agent_state") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(limit)
        
        if agent_name:
            query = query.eq("agent_name", agent_name)
        
        result = query.execute()
        return result.data or []
