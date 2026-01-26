#!/usr/bin/env python
"""
Run Subscription Scheduler

Standalone script to process subscription schedules.
Can be run via cron job at the start of each month.

Usage:
    python scripts/run_subscription_scheduler.py [--dry-run]
    
Arguments:
    --dry-run    Only log what would happen, don't make changes
"""
import sys
import os
import logging
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from utils.subscription_scheduler import process_monthly_subscription_schedules, MONTH_NAMES
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Process subscription schedules for the current month')
    parser.add_argument('--dry-run', action='store_true', help='Only log changes, do not apply them')
    args = parser.parse_args()
    
    current_month = datetime.now().month
    logger.info("=" * 60)
    logger.info(f"SUBSCRIPTION SCHEDULER - {MONTH_NAMES[current_month]} {datetime.now().year}")
    logger.info("=" * 60)
    
    if args.dry_run:
        logger.info("*** DRY RUN MODE - No changes will be made ***")
    
    results = process_monthly_subscription_schedules(dry_run=args.dry_run)
    
    logger.info("-" * 60)
    logger.info("RESULTS SUMMARY")
    logger.info("-" * 60)
    logger.info(f"Subscriptions Paused:  {len(results['paused'])}")
    logger.info(f"Subscriptions Resumed: {len(results['resumed'])}")
    logger.info(f"Errors:                {len(results['errors'])}")
    
    if results['paused']:
        logger.info("\nPaused Subscriptions:")
        for item in results['paused']:
            logger.info(f"  - Customer {item['customer_id']}: {item['email']} ({item['plan']})")
    
    if results['resumed']:
        logger.info("\nResumed Subscriptions:")
        for item in results['resumed']:
            logger.info(f"  - Customer {item['customer_id']}: {item['email']} ({item['plan']})")
    
    if results['errors']:
        logger.error("\nErrors encountered:")
        for err in results['errors']:
            logger.error(f"  - {err}")
    
    logger.info("=" * 60)
    logger.info("Scheduler complete")
    
    return 0 if not results['errors'] else 1


if __name__ == "__main__":
    sys.exit(main())
