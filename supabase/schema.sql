-- Casa Hunt - Supabase Database Schema
-- Run this in Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Listings Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS listings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source TEXT NOT NULL,  -- 'imobiliare.ro' or 'storia.ro'
    external_id TEXT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    price_raw TEXT,
    price_eur INTEGER,
    location TEXT,
    surface_mp INTEGER,
    rooms INTEGER,
    features_raw TEXT,
    metro_nearby BOOLEAN DEFAULT FALSE,
    
    -- Scoring fields (added by Analyzer)
    score INTEGER,
    analyzed_at TIMESTAMP WITH TIME ZONE,
    
    -- Decision fields (added by Decision Agent)
    decision TEXT,  -- 'APPROVE' or 'REJECT'
    decision_reason TEXT,
    decided_at TIMESTAMP WITH TIME ZONE,
    
    -- Notification tracking
    notified_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    scraped_at TIMESTAMP WITH TIME ZONE NOT NULL,
    raw_data JSONB,  -- Original scraped data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for listings
CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
CREATE INDEX IF NOT EXISTS idx_listings_score ON listings(score) WHERE score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listings_decision ON listings(decision) WHERE decision IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_eur);
CREATE INDEX IF NOT EXISTS idx_listings_created ON listings(created_at DESC);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER IF NOT EXISTS update_listings_updated_at
    BEFORE UPDATE ON listings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Missions Table (Task Queue)
-- ============================================================================

CREATE TABLE IF NOT EXISTS missions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type TEXT NOT NULL,  -- 'scrape', 'analyze', 'decide', 'notify'
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    payload JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Retry tracking
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for missions
CREATE INDEX IF NOT EXISTS idx_missions_type_status ON missions(type, status);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_missions_created ON missions(created_at DESC);

-- ============================================================================
-- Events Table (Event Bus)
-- ============================================================================

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type TEXT NOT NULL,  -- 'listings_scraped', 'listing_analyzed', 'listing_decided', etc.
    payload JSONB NOT NULL DEFAULT '{}',
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP WITH TIME ZONE,
    source_agent TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for events
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);

-- ============================================================================
-- Agent State Table (Monitoring)
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,  -- 'scout', 'analyzer', 'decision', 'notifier'
    agent_version TEXT,
    state TEXT NOT NULL,  -- 'running', 'completed', 'failed', 'idle'
    details JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for agent_state
CREATE INDEX IF NOT EXISTS idx_agent_state_name ON agent_state(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_state_created ON agent_state(created_at DESC);

-- ============================================================================
-- Row Level Security (RLS)
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_state ENABLE ROW LEVEL SECURITY;

-- Create policies for authenticated users
CREATE POLICY "Allow all operations for authenticated users" ON listings
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "Allow all operations for authenticated users" ON missions
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "Allow all operations for authenticated users" ON events
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "Allow all operations for authenticated users" ON agent_state
    FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to get pending missions by type
CREATE OR REPLACE FUNCTION get_pending_missions(mission_type TEXT)
RETURNS TABLE (
    id UUID,
    type TEXT,
    status TEXT,
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.type, m.status, m.payload, m.created_at
    FROM missions m
    WHERE m.type = mission_type AND m.status = 'pending'
    ORDER BY m.created_at ASC
    LIMIT 100;
END;
$$ LANGUAGE plpgsql;

-- Function to get unprocessed events
CREATE OR REPLACE FUNCTION get_unprocessed_events(event_type TEXT DEFAULT NULL)
RETURNS TABLE (
    id UUID,
    type TEXT,
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    IF event_type IS NULL THEN
        RETURN QUERY
        SELECT e.id, e.type, e.payload, e.created_at
        FROM events e
        WHERE e.processed = FALSE
        ORDER BY e.created_at ASC
        LIMIT 100;
    ELSE
        RETURN QUERY
        SELECT e.id, e.type, e.payload, e.created_at
        FROM events e
        WHERE e.processed = FALSE AND e.type = event_type
        ORDER BY e.created_at ASC
        LIMIT 100;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to mark events as processed
CREATE OR REPLACE FUNCTION mark_events_processed(event_ids UUID[])
RETURNS VOID AS $$
BEGIN
    UPDATE events
    SET processed = TRUE, processed_at = NOW()
    WHERE id = ANY(event_ids);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Sample Data (Optional)
-- ============================================================================

-- Insert a test listing (optional)
-- INSERT INTO listings (source, url, title, price_raw, price_eur, location, scraped_at)
-- VALUES (
--     'test',
--     'https://example.com/test',
--     'Test Listing',
--     '150.000 €',
--     150000,
--     'Sector 3, Bucuresti',
--     NOW()
-- );
