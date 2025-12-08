#!/usr/bin/env python3
"""
Test script to verify WHOIS info collection.

CURRENT STATUS: WHOIS collection is NOT implemented in the codebase.
This script provides a working implementation for testing purposes.

WHOIS data is valuable for the Provenance dimension of Trust Stack:
- Domain age (older domains are generally more trustworthy)
- Registrar reputation
- Registration privacy (WHOIS protection can be a red flag)
- Domain expiration (domains expiring soon may indicate temporary/suspicious sites)

Usage:
    python scripts/test_whois_collection.py [--domain DOMAIN] [--verbose]

Requirements:
    pip install python-whois
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, Optional, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_whois_implementation_status():
    """Check if WHOIS is implemented in the codebase."""
    print("\n" + "=" * 60)
    print("WHOIS IMPLEMENTATION STATUS CHECK")
    print("=" * 60)
    
    # Check config/settings.py for WHOIS endpoint
    settings_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'settings.py'
    )
    
    whois_configured = False
    if os.path.exists(settings_path):
        with open(settings_path, 'r') as f:
            content = f.read()
            if 'whois' in content.lower():
                whois_configured = True
                print("✅ WHOIS endpoint configured in config/settings.py")
    
    # Check for actual WHOIS implementation files
    ingestion_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'ingestion'
    )
    
    whois_files = []
    for root, dirs, files in os.walk(ingestion_dir):
        for f in files:
            if 'whois' in f.lower():
                whois_files.append(os.path.join(root, f))
    
    if whois_files:
        print(f"✅ WHOIS implementation files found: {whois_files}")
    else:
        print("❌ No WHOIS implementation files found in ingestion/")
    
    # Check for whois in attribute_detector
    detector_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'scoring', 'attribute_detector.py'
    )
    
    whois_in_detector = False
    if os.path.exists(detector_path):
        with open(detector_path, 'r') as f:
            content = f.read()
            if 'whois' in content.lower() or 'domain_age' in content.lower():
                whois_in_detector = True
                print("✅ WHOIS/domain_age detection found in attribute_detector.py")
            else:
                print("❌ No WHOIS/domain_age detection in attribute_detector.py")
    
    # Summary
    print("\n" + "-" * 60)
    print("SUMMARY:")
    if whois_configured and not whois_files and not whois_in_detector:
        print("⚠️  WHOIS is CONFIGURED but NOT IMPLEMENTED")
        print("   The endpoint is defined but no actual lookup code exists.")
        return False
    elif whois_files or whois_in_detector:
        print("✅ WHOIS collection appears to be implemented")
        return True
    else:
        print("❌ WHOIS collection is NOT configured or implemented")
        return False


class WHOISLookup:
    """
    WHOIS lookup utility for testing domain registration info.
    
    This is a TEST IMPLEMENTATION - to integrate into the main app:
    1. Add this to ingestion/whois_lookup.py
    2. Call from attribute_detector.py for provenance scoring
    3. Store results in content.meta['whois_*']
    """
    
    def __init__(self):
        self.whois_available = False
        try:
            import whois
            self.whois = whois
            self.whois_available = True
        except ImportError:
            logger.warning("python-whois not installed. Run: pip install python-whois")
    
    def lookup(self, domain: str) -> Dict[str, Any]:
        """
        Perform WHOIS lookup for a domain.
        
        Args:
            domain: Domain name to look up (e.g., 'nike.com')
            
        Returns:
            Dict with WHOIS data including:
            - domain_name: Registered domain name
            - registrar: Domain registrar
            - creation_date: When domain was registered
            - expiration_date: When domain expires
            - updated_date: Last update date
            - domain_age_days: Age of domain in days
            - name_servers: List of name servers
            - status: Domain status codes
            - whois_privacy: Whether WHOIS privacy is enabled
            - registrant_country: Country of registrant (if available)
        """
        if not self.whois_available:
            return {
                'error': 'python-whois not installed',
                'domain': domain
            }
        
        try:
            # Clean domain (remove protocol, path, etc.)
            if '://' in domain:
                from urllib.parse import urlparse
                domain = urlparse(domain).netloc
            
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Perform lookup
            w = self.whois.whois(domain)
            
            # Extract and normalize data
            result = {
                'domain': domain,
                'domain_name': self._normalize_field(w.domain_name),
                'registrar': self._normalize_field(w.registrar),
                'creation_date': self._normalize_date(w.creation_date),
                'expiration_date': self._normalize_date(w.expiration_date),
                'updated_date': self._normalize_date(w.updated_date),
                'name_servers': self._normalize_list(w.name_servers),
                'status': self._normalize_list(w.status),
                'registrant_country': self._normalize_field(getattr(w, 'country', None)),
                'registrant_org': self._normalize_field(getattr(w, 'org', None)),
                'registrant_state': self._normalize_field(getattr(w, 'state', None)),
            }
            
            # Calculate domain age
            creation = result.get('creation_date')
            if creation and isinstance(creation, datetime):
                # Handle timezone-aware datetimes
                now = datetime.now()
                if creation.tzinfo is not None:
                    # Make creation naive by removing timezone
                    creation = creation.replace(tzinfo=None)
                age_days = (now - creation).days
                result['domain_age_days'] = age_days
                result['domain_age_years'] = round(age_days / 365.25, 1)
            else:
                result['domain_age_days'] = None
                result['domain_age_years'] = None
            
            # Detect WHOIS privacy
            org = result.get('registrant_org', '') or ''
            privacy_indicators = [
                'privacy', 'proxy', 'protected', 'whoisguard', 
                'domains by proxy', 'contact privacy', 'redacted'
            ]
            result['whois_privacy'] = any(
                indicator in org.lower() 
                for indicator in privacy_indicators
            )
            
            # Calculate trust signals
            result['trust_signals'] = self._calculate_trust_signals(result)
            
            return result
            
        except Exception as e:
            logger.error(f"WHOIS lookup failed for {domain}: {e}")
            return {
                'error': str(e),
                'domain': domain
            }
    
    def _normalize_field(self, value) -> Optional[str]:
        """Normalize a single WHOIS field."""
        if value is None:
            return None
        if isinstance(value, list):
            return value[0] if value else None
        return str(value)
    
    def _normalize_date(self, value) -> Optional[datetime]:
        """Normalize a date field."""
        if value is None:
            return None
        if isinstance(value, list):
            return value[0] if value else None
        return value
    
    def _normalize_list(self, value) -> list:
        """Normalize a list field."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return list(value) if value else []
    
    def _calculate_trust_signals(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate trust signals based on WHOIS data.
        
        These signals can be used in the Provenance dimension scoring.
        """
        signals = {}
        
        # Domain age signal (1-10 scale)
        age_years = data.get('domain_age_years')
        if age_years is not None:
            if age_years >= 10:
                signals['domain_age_score'] = 10.0
                signals['domain_age_assessment'] = 'Well-established domain (10+ years)'
            elif age_years >= 5:
                signals['domain_age_score'] = 8.0
                signals['domain_age_assessment'] = 'Established domain (5-10 years)'
            elif age_years >= 2:
                signals['domain_age_score'] = 6.0
                signals['domain_age_assessment'] = 'Moderate age domain (2-5 years)'
            elif age_years >= 1:
                signals['domain_age_score'] = 4.0
                signals['domain_age_assessment'] = 'Young domain (1-2 years)'
            else:
                signals['domain_age_score'] = 2.0
                signals['domain_age_assessment'] = 'Very young domain (<1 year)'
        else:
            signals['domain_age_score'] = None
            signals['domain_age_assessment'] = 'Unable to determine domain age'
        
        # WHOIS privacy signal
        if data.get('whois_privacy'):
            signals['privacy_score'] = 3.0  # Privacy can be legitimate but is a yellow flag
            signals['privacy_assessment'] = 'WHOIS privacy enabled - registrant info hidden'
        else:
            signals['privacy_score'] = 7.0
            signals['privacy_assessment'] = 'WHOIS info publicly visible'
        
        # Expiration signal
        expiration = data.get('expiration_date')
        if expiration and isinstance(expiration, datetime):
            now = datetime.now()
            # Handle timezone-aware datetimes
            if expiration.tzinfo is not None:
                expiration = expiration.replace(tzinfo=None)
            days_until_expiry = (expiration - now).days
            if days_until_expiry < 30:
                signals['expiration_score'] = 2.0
                signals['expiration_assessment'] = f'Domain expires soon ({days_until_expiry} days)'
            elif days_until_expiry < 90:
                signals['expiration_score'] = 5.0
                signals['expiration_assessment'] = f'Domain expires in {days_until_expiry} days'
            elif days_until_expiry < 365:
                signals['expiration_score'] = 7.0
                signals['expiration_assessment'] = f'Domain valid for {days_until_expiry} days'
            else:
                signals['expiration_score'] = 9.0
                signals['expiration_assessment'] = f'Domain valid for {days_until_expiry // 365}+ years'
        
        return signals


def test_whois_lookup(domain: str, verbose: bool = False):
    """Test WHOIS lookup for a domain."""
    print("\n" + "=" * 60)
    print(f"WHOIS LOOKUP TEST: {domain}")
    print("=" * 60)
    
    lookup = WHOISLookup()
    
    if not lookup.whois_available:
        print("\n❌ python-whois not installed")
        print("   Run: pip install python-whois")
        return None
    
    print("\n[1] Performing WHOIS lookup...")
    result = lookup.lookup(domain)
    
    if 'error' in result:
        print(f"\n❌ WHOIS lookup failed: {result['error']}")
        return None
    
    print(f"    ✅ WHOIS lookup successful")
    
    # Display basic info
    print("\n[2] Domain Registration Info:")
    print(f"    Domain: {result.get('domain_name', 'N/A')}")
    print(f"    Registrar: {result.get('registrar', 'N/A')}")
    
    creation = result.get('creation_date')
    if creation:
        print(f"    Created: {creation.strftime('%Y-%m-%d') if hasattr(creation, 'strftime') else creation}")
    
    expiration = result.get('expiration_date')
    if expiration:
        print(f"    Expires: {expiration.strftime('%Y-%m-%d') if hasattr(expiration, 'strftime') else expiration}")
    
    age_years = result.get('domain_age_years')
    if age_years:
        print(f"    Domain Age: {age_years} years ({result.get('domain_age_days', 'N/A')} days)")
    
    # Display trust signals
    signals = result.get('trust_signals', {})
    if signals:
        print("\n[3] Trust Signals (for Provenance scoring):")
        
        age_score = signals.get('domain_age_score')
        if age_score:
            print(f"    Domain Age Score: {age_score}/10")
            print(f"    Assessment: {signals.get('domain_age_assessment', 'N/A')}")
        
        privacy_score = signals.get('privacy_score')
        if privacy_score:
            print(f"    Privacy Score: {privacy_score}/10")
            print(f"    Assessment: {signals.get('privacy_assessment', 'N/A')}")
        
        exp_score = signals.get('expiration_score')
        if exp_score:
            print(f"    Expiration Score: {exp_score}/10")
            print(f"    Assessment: {signals.get('expiration_assessment', 'N/A')}")
    
    if verbose:
        print("\n[4] Full WHOIS Data:")
        for key, value in result.items():
            if key != 'trust_signals':
                print(f"    {key}: {value}")
    
    # Summary
    print("\n" + "-" * 60)
    print("SUMMARY:")
    overall_score = None
    if signals.get('domain_age_score') and signals.get('privacy_score'):
        scores = [s for s in [
            signals.get('domain_age_score'),
            signals.get('privacy_score'),
            signals.get('expiration_score')
        ] if s is not None]
        overall_score = sum(scores) / len(scores) if scores else None
    
    if overall_score:
        print(f"Composite WHOIS Trust Score: {overall_score:.1f}/10")
        if overall_score >= 7:
            print("✅ Domain appears trustworthy based on WHOIS data")
        elif overall_score >= 5:
            print("⚠️ Domain has some trust concerns")
        else:
            print("❌ Domain has significant trust flags")
    
    return result


def run_all_tests(domain: str = None, verbose: bool = False):
    """Run all WHOIS collection tests."""
    print("\n" + "=" * 70)
    print("          WHOIS COLLECTION VERIFICATION TEST SUITE")
    print("=" * 70)
    
    # Check implementation status
    is_implemented = check_whois_implementation_status()
    
    # If not implemented, explain what needs to be done
    if not is_implemented:
        print("\n" + "=" * 60)
        print("HOW TO IMPLEMENT WHOIS COLLECTION")
        print("=" * 60)
        print("""
1. Install the python-whois library:
   pip install python-whois

2. Add WHOIS lookup to ingestion/whois_lookup.py:
   - Copy the WHOISLookup class from this test script

3. Integrate with attribute_detector.py:
   - Add _detect_domain_age() method
   - Add _detect_whois_privacy() method
   - Call WHOIS lookup for each unique domain

4. Store WHOIS data in content.meta:
   - content.meta['whois_domain_age_years'] = age
   - content.meta['whois_privacy'] = True/False
   - content.meta['whois_registrar'] = registrar_name

5. Add signals to config/signals.json:
   - domain_age (Provenance dimension)
   - whois_privacy_flag (Provenance dimension)
   - domain_expiration_risk (Provenance dimension)
""")
    
    # Run WHOIS lookup test
    whois_result = None
    if domain:
        whois_result = test_whois_lookup(domain, verbose)
    else:
        # Test with a well-known domain
        print("\n[Testing with example domain: google.com]")
        whois_result = test_whois_lookup('google.com', verbose)
    
    # Final results
    print("\n" + "=" * 70)
    print("                    FINAL TEST RESULTS")
    print("=" * 70)
    
    print(f"WHOIS in codebase: {'❌ NOT IMPLEMENTED' if not is_implemented else '✅ IMPLEMENTED'}")
    print(f"WHOIS lookup test: {'✅ PASS' if whois_result and 'error' not in whois_result else '❌ FAIL'}")
    
    if whois_result and 'error' not in whois_result:
        print("\n📊 WHOIS data that COULD be collected for Provenance scoring:")
        print("  - Domain age (older = more trustworthy)")
        print("  - Registrar reputation")
        print("  - WHOIS privacy status (hidden info can be a flag)")
        print("  - Domain expiration date (soon-to-expire = risk)")
        print("  - Registrant organization/country")
    
    return whois_result is not None and 'error' not in whois_result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test WHOIS info collection')
    parser.add_argument('--domain', '-d', type=str, 
                        help='Domain to look up (e.g., nike.com)')
    parser.add_argument('--verbose', '-v', action='store_true', 
                        help='Show detailed output')
    args = parser.parse_args()
    
    success = run_all_tests(domain=args.domain, verbose=args.verbose)
    sys.exit(0 if success else 1)
