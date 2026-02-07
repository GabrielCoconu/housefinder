#!/usr/bin/env python3
"""
Casa Hunt - Scraper Utilities
Shared utilities and data structures for all scraper modules.
"""

import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse


@dataclass
class Listing:
    """
    Standardized listing data structure.
    Used across all scraper modules for consistent data handling.
    """
    # Required fields
    url: str
    title: str
    source: str  # 'imobiliare.ro' or 'storia.ro'
    
    # Pricing
    price_eur: Optional[int] = None
    price_raw: str = ""
    
    # Location
    location: str = ""
    
    # Property details
    surface_mp: Optional[int] = None
    rooms: Optional[int] = None
    
    # Metadata
    description: str = ""
    features_raw: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Derived fields (set during processing)
    id: str = ""
    is_in_target_area: bool = False
    has_metro_nearby: bool = False
    is_under_budget: bool = False
    
    def __post_init__(self):
        """Generate ID from URL hash if not provided."""
        if not self.id:
            self.id = calculate_url_hash(self.url)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Listing':
        """Create Listing from dictionary."""
        # Filter only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)


# Metro-related keywords for proximity detection
METRO_KEYWORDS = [
    'metrou', 'statie', 'statia', 'metro',
    'm1', 'm2', 'm3', 'm4', 'm5', 'm6',
    'pipera', 'universitate', 'romana', 'victoriei', 'piata victoriei',
    'pallady', 'berceni', 'dimitrie leonida', 'tudor arghezi',
    'aparatorii patriei', 'constantin brancoveanu', 'piata sudului',
    'erior nord', 'erior sud', 'crangasi', 'gorjului', 'lujerului',
    'politehnica', 'eroilor', 'izvor', 'piata unirii', 'timpuri noi',
    'mihai bravu', 'dristor', 'grigorescu', 'obor', 'piata spaniei',
    'romancierilor', 'parcul carol', 'tineretului', 'calarasilor',
    'dristor', 'republica', 'pantelimon', 'anghel saligny',
    'berceni', 'bragadiru', 'popesti-leordeni', 'chiajna', 'voluntari',
    'otopeni', 'buftea', 'magurele', 'corbeanca', 'snagov'
]

# Bucharest and Ilfov area keywords
TARGET_AREA_KEYWORDS = [
    'bucuresti', 'bucharest',
    'ilfov', 'sector 1', 'sector 2', 'sector 3', 'sector 4', 'sector 5', 'sector 6',
    'berceni', 'bragadiru', 'popesti', 'popesti-leordeni', 'chiajna', 'voluntari',
    'otopeni', 'buftea', 'magurele', 'corbeanca', 'snagov', 'mogosoaia',
    'balotesti', 'tunari', 'afumati', 'pantelimon', 'dobroesti', 'fundeni',
    'glina', 'cernica', 'branesti', 'ganeasa', 'domnesti', 'clinceni',
    'bragadiru', 'ciorogarla', 'darasti', 'joita', 'tanganu', 'varteju'
]


def calculate_url_hash(url: str) -> str:
    """
    Calculate a short unique hash for a URL.
    Used for deduplication.
    
    Args:
        url: The URL to hash
        
    Returns:
        12-character hexadecimal hash string
    """
    return hashlib.md5(url.encode('utf-8')).hexdigest()[:12]


def normalize_url(url: str) -> str:
    """
    Normalize URL for comparison.
    Removes tracking parameters, fragments, etc.
    
    Args:
        url: Raw URL
        
    Returns:
        Normalized URL
    """
    # Parse URL
    parsed = urlparse(url)
    
    # Rebuild without fragment and query params that don't affect content
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    
    return normalized.lower().rstrip('/')


def merge_listings(listings: List[Listing]) -> List[Listing]:
    """
    Merge listings and remove duplicates based on URL hash.
    
    Args:
        listings: List of Listing objects
        
    Returns:
        List of unique Listing objects
    """
    seen_hashes = set()
    unique_listings = []
    
    for listing in listings:
        url_hash = calculate_url_hash(listing.url)
        if url_hash not in seen_hashes:
            seen_hashes.add(url_hash)
            listing.id = url_hash
            unique_listings.append(listing)
    
    return unique_listings


def has_metro_proximity(location_text: str) -> bool:
    """
    Check if location mentions metro access or proximity.
    
    Args:
        location_text: Location description
        
    Returns:
        True if metro-related keywords found
    """
    if not location_text:
        return False
    
    location_lower = location_text.lower()
    return any(keyword in location_lower for keyword in METRO_KEYWORDS)


def is_within_budget(price: Optional[int], budget: int) -> bool:
    """
    Check if price is within budget.
    
    Args:
        price: Price in EUR (None if unknown)
        budget: Maximum budget
        
    Returns:
        True if price is within budget or unknown
    """
    if price is None:
        return True  # Include unknown prices
    return price <= budget


def filter_bucharest_ilfov(listings: List[Listing]) -> List[Listing]:
    """
    Filter listings for Bucharest/Ilfov area.
    
    Args:
        listings: List of Listing objects
        
    Returns:
        Filtered list of listings in target area
    """
    filtered = []
    
    for listing in listings:
        location = (listing.location or "").lower()
        
        # Check if any target area keyword matches
        is_in_area = any(keyword in location for keyword in TARGET_AREA_KEYWORDS)
        
        if is_in_area:
            listing.is_in_target_area = True
            filtered.append(listing)
    
    return filtered


def extract_price(price_text: Optional[str]) -> Optional[int]:
    """
    Extract numeric price from text.
    Handles various formats like "200.000 EUR", "200000", "200 000 €"
    
    Args:
        price_text: Raw price text
        
    Returns:
        Price as integer or None if not found
    """
    if not price_text:
        return None
    
    # Remove non-digit characters except for separators
    # Handle both dot (200.000) and space (200 000) separators
    cleaned = re.sub(r'[^\d]', '', price_text)
    
    if cleaned:
        try:
            return int(cleaned)
        except ValueError:
            return None
    
    return None


def extract_surface(text: Optional[str]) -> Optional[int]:
    """
    Extract surface area in square meters from text.
    
    Args:
        text: Text containing surface information
        
    Returns:
        Surface area as integer or None
    """
    if not text:
        return None
    
    # Match patterns like "120 mp", "120 m²", "120mp", "120 m2"
    match = re.search(r'(\d+)\s*(?:mp|m²|m2|sqm)', text.lower())
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    
    return None


def extract_rooms(text: Optional[str]) -> Optional[int]:
    """
    Extract number of rooms from text.
    
    Args:
        text: Text containing room information
        
    Returns:
        Number of rooms as integer or None
    """
    if not text:
        return None
    
    # Match patterns like "4 camere", "4 cam", "4 rooms"
    match = re.search(r'(\d+)\s*(?:cam|camera|camere|rooms?)', text.lower())
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    
    return None


def format_price(price: Optional[int]) -> str:
    """
    Format price for display.
    
    Args:
        price: Price in EUR
        
    Returns:
        Formatted price string
    """
    if price is None:
        return "N/A"
    return f"{price:,} EUR".replace(",", ".")


def ensure_output_dir(output_dir: str) -> str:
    """
    Ensure output directory exists, create if needed.
    
    Args:
        output_dir: Path to output directory
        
    Returns:
        Absolute path to output directory
    """
    abs_path = os.path.abspath(output_dir)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path


def setup_logging(level: int = logging.INFO, 
                  log_file: Optional[str] = None,
                  console: bool = True) -> logging.Logger:
    """
    Setup logging configuration.
    
    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path for logging
        console: Whether to log to console
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def load_seen_urls(output_dir: str) -> set:
    """
    Load previously seen URLs from persistence file.
    
    Args:
        output_dir: Directory containing the seen URLs file
        
    Returns:
        Set of seen URL hashes
    """
    seen_file = os.path.join(output_dir, '.seen_urls')
    if os.path.exists(seen_file):
        with open(seen_file, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_seen_url(url: str, output_dir: str) -> None:
    """
    Save URL to seen URLs file.
    
    Args:
        url: URL to save
        output_dir: Directory for the seen URLs file
    """
    seen_file = os.path.join(output_dir, '.seen_urls')
    url_hash = calculate_url_hash(url)
    
    with open(seen_file, 'a', encoding='utf-8') as f:
        f.write(f"{url_hash}\n")


def sanitize_filename(text: str) -> str:
    """
    Sanitize text for use in filename.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized filename-safe string
    """
    # Remove or replace invalid characters
    sanitized = re.sub(r'[^\w\s-]', '', text)
    sanitized = re.sub(r'[-\s]+', '-', sanitized)
    return sanitized.strip('-')[:50]
