#!/usr/bin/env python3
"""
Casa Hunt - Main Orchestrator
Combines multiple scraper modules into a unified house hunting system.

This script orchestrates scraping from multiple sources (Imobiliare.ro, Storia.ro),
merges results, removes duplicates, filters for target criteria, and outputs
structured data with statistics.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

# Import scraper modules
from imobiliare_scraper import scrape_imobiliare
from storia_scraper import scrape_storia
from scraper_utils import (
    calculate_url_hash,
    filter_bucharest_ilfov,
    has_metro_proximity,
    is_within_budget,
    setup_logging,
    ensure_output_dir,
    format_price,
    merge_listings,
    Listing
)


@dataclass
class ScrapingStats:
    """Statistics container for scraping results."""
    total_listings: int = 0
    unique_listings: int = 0
    duplicates_removed: int = 0
    bucharest_ilfov_listings: int = 0
    with_metro_access: int = 0
    under_budget: int = 0
    imobiliare_count: int = 0
    storia_count: int = 0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def print_summary(self):
        """Print formatted summary to console."""
        print("\n" + "=" * 60)
        print("  CASA HUNT - SCRAPING SUMMARY")
        print("=" * 60)
        print(f"  📊 Total Listings Scraped:    {self.total_listings}")
        print(f"  ✨ Unique Listings:           {self.unique_listings}")
        print(f"  🗑️  Duplicates Removed:        {self.duplicates_removed}")
        print(f"  📍 Bucharest/Ilfov Area:      {self.bucharest_ilfov_listings}")
        print(f"  🚇 With Metro Access:         {self.with_metro_access}")
        print(f"  💰 Under Budget (<200k EUR):  {self.under_budget}")
        print(f"  📦 Imobiliare.ro:             {self.imobiliare_count}")
        print(f"  📦 Storia.ro:                 {self.storia_count}")
        if self.errors:
            print(f"  ⚠️  Errors Encountered:        {len(self.errors)}")
        print("=" * 60)


class CasaHunt:
    """
    Main orchestrator class for the Casa Hunt system.
    
    Coordinates multiple scrapers, handles data merging, filtering,
    and result persistence.
    """
    
    DEFAULT_BUDGET_EUR = 200000
    DEFAULT_OUTPUT_DIR = "./output"
    
    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR, 
                 budget: int = DEFAULT_BUDGET_EUR,
                 max_pages: int = 3):
        """
        Initialize CasaHunt orchestrator.
        
        Args:
            output_dir: Directory for saving results
            budget: Maximum price in EUR
            max_pages: Maximum pages to scrape per source
        """
        self.output_dir = output_dir
        self.budget = budget
        self.max_pages = max_pages
        self.logger = logging.getLogger(__name__)
        self.stats = ScrapingStats()
        
    def run(self) -> Dict[str, Any]:
        """
        Execute the complete scraping workflow.
        
        Returns:
            Dictionary containing all results and metadata
        """
        self.logger.info("=" * 60)
        self.logger.info("CASA HUNT - House Hunting System Starting")
        self.logger.info("=" * 60)
        
        # Ensure output directory exists
        ensure_output_dir(self.output_dir)
        
        # Collect all listings
        all_listings: List[Listing] = []
        
        # Run Imobiliare scraper
        self.logger.info("\n[1/2] Running Imobiliare.ro scraper...")
        try:
            imobiliare_listings = scrape_imobiliare(max_pages=self.max_pages)
            self.logger.info(f"  ✓ Found {len(imobiliare_listings)} listings")
            all_listings.extend(imobiliare_listings)
            self.stats.imobiliare_count = len(imobiliare_listings)
        except Exception as e:
            error_msg = f"Imobiliare scraper failed: {str(e)}"
            self.logger.error(f"  ✗ {error_msg}")
            self.stats.errors.append(error_msg)
            imobiliare_listings = []
        
        # Run Storia scraper
        self.logger.info("\n[2/2] Running Storia.ro scraper...")
        try:
            storia_listings = scrape_storia(max_pages=self.max_pages)
            self.logger.info(f"  ✓ Found {len(storia_listings)} listings")
            all_listings.extend(storia_listings)
            self.stats.storia_count = len(storia_listings)
        except Exception as e:
            error_msg = f"Storia scraper failed: {str(e)}"
            self.logger.error(f"  ✗ {error_msg}")
            self.stats.errors.append(error_msg)
            storia_listings = []
        
        # Update total before deduplication
        self.stats.total_listings = len(all_listings)
        
        # Merge and deduplicate
        self.logger.info("\n[3/3] Merging and deduplicating results...")
        unique_listings = merge_listings(all_listings)
        self.stats.duplicates_removed = len(all_listings) - len(unique_listings)
        self.stats.unique_listings = len(unique_listings)
        self.logger.info(f"  ✓ {self.stats.unique_listings} unique listings")
        self.logger.info(f"  ✓ {self.stats.duplicates_removed} duplicates removed")
        
        # Filter for Bucharest/Ilfov area
        self.logger.info("\n[4/4] Filtering for Bucharest/Ilfov area...")
        filtered_listings = filter_bucharest_ilfov(unique_listings)
        self.stats.bucharest_ilfov_listings = len(filtered_listings)
        self.logger.info(f"  ✓ {self.stats.bucharest_ilfov_listings} listings in target area")
        
        # Calculate statistics
        self.logger.info("\n[5/5] Calculating statistics...")
        
        # Count metro access
        metro_listings = [l for l in filtered_listings if has_metro_proximity(l.location)]
        self.stats.with_metro_access = len(metro_listings)
        
        # Count under budget
        budget_listings = [l for l in filtered_listings if is_within_budget(l.price_eur, self.budget)]
        self.stats.under_budget = len(budget_listings)
        
        # Enrich listings with derived fields
        for listing in filtered_listings:
            listing.is_in_target_area = True
            listing.has_metro_nearby = has_metro_proximity(listing.location)
            listing.is_under_budget = is_within_budget(listing.price_eur, self.budget)
        
        self.logger.info(f"  ✓ {self.stats.with_metro_access} with metro access")
        self.logger.info(f"  ✓ {self.stats.under_budget} under budget")
        
        # Prepare final result
        timestamp = datetime.now()
        result = {
            "metadata": {
                "timestamp": timestamp.isoformat(),
                "date": timestamp.strftime("%Y-%m-%d"),
                "time": timestamp.strftime("%H:%M:%S"),
                "version": "1.0.0",
                "sources": ["imobiliare.ro", "storia.ro"],
                "criteria": {
                    "location": "Bucharest + Ilfov periphery",
                    "max_price_eur": self.budget,
                    "property_type": "houses/villas",
                    "metro_access": "preferred"
                }
            },
            "statistics": self.stats.to_dict(),
            "listings": [l.to_dict() for l in filtered_listings]
        }
        
        # Save to JSON
        output_file = self._save_results(result, timestamp)
        
        # Print summary
        self.stats.print_summary()
        print(f"\n  💾 Results saved to: {output_file}")
        
        return result
    
    def _save_results(self, result: Dict[str, Any], timestamp: datetime) -> str:
        """
        Save results to JSON file with timestamp in filename.
        
        Args:
            result: The complete result dictionary
            timestamp: Timestamp for filename
            
        Returns:
            Path to saved file
        """
        filename = f"casa_hunt_{timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"\n💾 Results saved to: {filepath}")
        return filepath


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description='Casa Hunt - Unified House Hunting System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --output-dir ./results
  %(prog)s --output-dir ./results --budget 180000 --max-pages 5
  %(prog)s -o ./results -b 150000 -p 2
        """
    )
    
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default=CasaHunt.DEFAULT_OUTPUT_DIR,
        help=f'Directory to save results (default: {CasaHunt.DEFAULT_OUTPUT_DIR})'
    )
    
    parser.add_argument(
        '--budget', '-b',
        type=int,
        default=CasaHunt.DEFAULT_BUDGET_EUR,
        help=f'Maximum budget in EUR (default: {CasaHunt.DEFAULT_BUDGET_EUR})'
    )
    
    parser.add_argument(
        '--max-pages', '-p',
        type=int,
        default=3,
        help='Maximum pages to scrape per source (default: 3)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose (DEBUG) logging'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress console output (log to file only)'
    )
    
    return parser


def main():
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(
        level=log_level,
        log_file=os.path.join(args.output_dir, 'casa_hunt.log'),
        console=not args.quiet
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize and run Casa Hunt
        casa_hunt = CasaHunt(
            output_dir=args.output_dir,
            budget=args.budget,
            max_pages=args.max_pages
        )
        
        result = casa_hunt.run()
        
        # Exit with error code if no listings found
        if result['statistics']['unique_listings'] == 0:
            logger.warning("No listings found. Check scraper configuration.")
            return 1
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n⛔ Scraping interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
