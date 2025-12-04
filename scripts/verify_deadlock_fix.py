import threading
import time
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from ingestion.playwright_manager import PlaywrightBrowserManager

def test_shutdown_deadlock():
    manager = PlaywrightBrowserManager()
    print("Starting manager...")
    # Mock the _run_browser_loop to avoid actually launching playwright (which might be slow/complex)
    # but we need to ensure it behaves like the real one regarding locks
    
    # Actually, let's use the real one but maybe mock the playwright part if possible?
    # The real one imports playwright inside the thread.
    # If playwright is not installed, it returns False.
    # Let's assume it starts.
    
    started = manager.start()
    if not started:
        print("Skipping test: Playwright not available or failed to start")
        return

    # Wait a bit
    time.sleep(1)
    
    print("Closing manager...")
    # This should not hang
    start_time = time.time()
    manager.close()
    end_time = time.time()
    
    print(f"Manager closed in {end_time - start_time:.2f} seconds")
    
    if end_time - start_time > 4.5:
        print("FAIL: Shutdown took too long, likely deadlocked (timeout is 5s)")
    else:
        print("PASS: Shutdown was quick")

if __name__ == "__main__":
    test_shutdown_deadlock()
