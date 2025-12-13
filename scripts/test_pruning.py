
import logging
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from data.store import init_db, session_scope, create_run, get_or_create_brand, get_or_create_scenario, prune_old_runs
from data.models import Run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_data_pruning():
    # 1. Setup DB
    if os.path.exists("test_pruning.db"):
        os.remove("test_pruning.db")
        
    # Use a separate test DB to avoid messing with real data
    os.environ["DATABASE_URL"] = "sqlite:///./test_pruning.db"
    engine = init_db()
    
    brand_slug = "test-brand-pruning"
    
    with session_scope(engine) as session:
        brand = get_or_create_brand(session, slug=brand_slug)
        scenario = get_or_create_scenario(session, slug="test-scenario")
        
        # 2. Plant OLD runs (older than 30 days)
        old_date = datetime.utcnow() - timedelta(days=40)
        logger.info(f"Creating OLD run at {old_date}")
        run_old = create_run(session, brand, scenario, external_id="run_old", config={})
        run_old.started_at = old_date # Manually override timestamp
        session.add(run_old)
        
        # 3. Plant RECENT runs (newer than 30 days)
        recent_date = datetime.utcnow() - timedelta(days=10)
        logger.info(f"Creating RECENT run at {recent_date}")
        run_recent = create_run(session, brand, scenario, external_id="run_recent", config={})
        run_recent.started_at = recent_date
        session.add(run_recent)
        
        session.commit()
    
    # 4. Verify baseline
    with session_scope(engine) as session:
        count = session.query(Run).count()
        logger.info(f"Baseline: {count} runs in DB")
        if count != 2:
            logger.error("Setup failed")
            return False
            
    # 5. Run Pruning
    logger.info("Running prune_old_runs(days_to_keep=30)...")
    with session_scope(engine) as session:
        deleted = prune_old_runs(session, days_to_keep=30)
        logger.info(f"Deleted {deleted} runs")
        
        remaining = session.query(Run).all()
        logger.info(f"Remaining runs: {len(remaining)}")
        
        if len(remaining) != 1:
            logger.error(f"FAILED: Expected 1 run remaining, got {len(remaining)}")
            return False
            
        if remaining[0].external_id != "run_recent":
             logger.error(f"FAILED: Wrong run remained: {remaining[0].external_id}")
             return False
             
    logger.info("Success: Pruning correctly deleted old run and kept recent one")
    
    # Cleanup
    if os.path.exists("test_pruning.db"):
        os.remove("test_pruning.db")
        
    return True

if __name__ == "__main__":
    if test_data_pruning():
        print("VERIFICATION PASSED")
        sys.exit(0)
    else:
        print("VERIFICATION FAILED")
        sys.exit(1)
