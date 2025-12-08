"""
WHOIS Lookup Module for Trust Stack Provenance Detection

Provides domain registration data for trust scoring:
- Domain age (older domains are generally more trustworthy)
- Registrar reputation
- WHOIS privacy status (hidden info can be a flag)
- Domain expiration risk
- Registrant organization/country
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Try to import python-whois
try:
    import whois
    WHOIS_AVAILABLE = True
except ImportError:
    WHOIS_AVAILABLE = False
    logger.warning("python-whois not installed. WHOIS lookups will be unavailable. Install with: pip install python-whois")


class WHOISLookup:
    """
    WHOIS lookup utility for domain registration information.
    
    Used by the attribute detector for Provenance dimension scoring.
    """
    
    # Cache for WHOIS results to avoid repeated lookups
    _cache: Dict[str, Dict[str, Any]] = {}
    
    def __init__(self):
        """Initialize the WHOIS lookup utility."""
        self.available = WHOIS_AVAILABLE
    
    @classmethod
    def clear_cache(cls):
        """Clear the WHOIS cache."""
        cls._cache.clear()
    
    def lookup(self, url_or_domain: str) -> Dict[str, Any]:
        """
        Perform WHOIS lookup for a domain.
        
        Args:
            url_or_domain: URL or domain name to look up (e.g., 'https://nike.com' or 'nike.com')
            
        Returns:
            Dict with WHOIS data including:
            - domain: Clean domain name
            - domain_name: Registered domain name
            - registrar: Domain registrar
            - creation_date: When domain was registered
            - expiration_date: When domain expires
            - domain_age_days: Age of domain in days
            - domain_age_years: Age of domain in years
            - whois_privacy: Whether WHOIS privacy is enabled
            - registrant_org: Registrant organization (if available)
            - registrant_country: Country of registrant (if available)
            - trust_signals: Dict of calculated trust signals
            - error: Error message if lookup failed
        """
        if not self.available:
            return {
                'error': 'python-whois not installed',
                'domain': url_or_domain
            }
        
        # Extract domain from URL
        domain = self._extract_domain(url_or_domain)
        if not domain:
            return {
                'error': 'Invalid domain',
                'domain': url_or_domain
            }
        
        # Check cache
        if domain in self._cache:
            logger.debug(f"WHOIS cache hit for {domain}")
            return self._cache[domain]
        
        try:
            logger.debug(f"Performing WHOIS lookup for {domain}")
            w = whois.whois(domain)
            
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
                now = datetime.now()
                if creation.tzinfo is not None:
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
                'domains by proxy', 'contact privacy', 'redacted',
                'privacy protect', 'domain protection'
            ]
            result['whois_privacy'] = any(
                indicator in org.lower() 
                for indicator in privacy_indicators
            )
            
            # Calculate trust signals
            result['trust_signals'] = self._calculate_trust_signals(result)
            
            # Cache the result
            self._cache[domain] = result
            
            logger.info(f"WHOIS lookup successful for {domain}: age={result.get('domain_age_years')} years")
            return result
            
        except Exception as e:
            logger.warning(f"WHOIS lookup failed for {domain}: {e}")
            error_result = {
                'error': str(e),
                'domain': domain
            }
            # Cache errors too (with shorter TTL in production)
            self._cache[domain] = error_result
            return error_result
    
    def _extract_domain(self, url_or_domain: str) -> Optional[str]:
        """Extract clean domain from URL or domain string."""
        if not url_or_domain:
            return None
        
        # If it looks like a URL, parse it
        if '://' in url_or_domain:
            try:
                parsed = urlparse(url_or_domain)
                domain = parsed.netloc
            except Exception:
                domain = url_or_domain
        else:
            domain = url_or_domain
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Remove port if present
        if ':' in domain:
            domain = domain.split(':')[0]
        
        return domain.lower() if domain else None
    
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
        
        These signals are used in the Provenance dimension scoring.
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
            elif age_years >= 0.5:
                signals['domain_age_score'] = 3.0
                signals['domain_age_assessment'] = 'Very young domain (6-12 months)'
            else:
                signals['domain_age_score'] = 2.0
                signals['domain_age_assessment'] = 'Brand new domain (<6 months)'
        else:
            signals['domain_age_score'] = None
            signals['domain_age_assessment'] = 'Unable to determine domain age'
        
        # WHOIS privacy signal
        if data.get('whois_privacy'):
            signals['privacy_score'] = 4.0  # Privacy can be legitimate but is a yellow flag
            signals['privacy_assessment'] = 'WHOIS privacy enabled - registrant info hidden'
        else:
            org = data.get('registrant_org')
            if org:
                signals['privacy_score'] = 8.0
                signals['privacy_assessment'] = f'WHOIS info publicly visible: {org}'
            else:
                signals['privacy_score'] = 6.0
                signals['privacy_assessment'] = 'WHOIS info visible but organization unknown'
        
        # Expiration signal
        expiration = data.get('expiration_date')
        if expiration and isinstance(expiration, datetime):
            now = datetime.now()
            if expiration.tzinfo is not None:
                expiration = expiration.replace(tzinfo=None)
            days_until_expiry = (expiration - now).days
            
            if days_until_expiry < 0:
                signals['expiration_score'] = 1.0
                signals['expiration_assessment'] = 'Domain is expired!'
            elif days_until_expiry < 30:
                signals['expiration_score'] = 2.0
                signals['expiration_assessment'] = f'Domain expires very soon ({days_until_expiry} days)'
            elif days_until_expiry < 90:
                signals['expiration_score'] = 5.0
                signals['expiration_assessment'] = f'Domain expires in {days_until_expiry} days'
            elif days_until_expiry < 365:
                signals['expiration_score'] = 7.0
                signals['expiration_assessment'] = f'Domain valid for {days_until_expiry} days'
            else:
                years = days_until_expiry // 365
                signals['expiration_score'] = 9.0
                signals['expiration_assessment'] = f'Domain valid for {years}+ years'
        else:
            signals['expiration_score'] = None
            signals['expiration_assessment'] = 'Unable to determine expiration date'
        
        # Registrar reputation (basic check for well-known registrars)
        registrar = (data.get('registrar') or '').lower()
        reputable_registrars = [
            'markmonitor', 'godaddy', 'namecheap', 'cloudflare', 
            'google', 'amazon', 'gandi', 'name.com', 'hover',
            'tucows', 'enom', 'network solutions', 'verisign'
        ]
        if any(rep in registrar for rep in reputable_registrars):
            signals['registrar_score'] = 8.0
            signals['registrar_assessment'] = f'Reputable registrar: {data.get("registrar")}'
        elif registrar:
            signals['registrar_score'] = 6.0
            signals['registrar_assessment'] = f'Registrar: {data.get("registrar")}'
        else:
            signals['registrar_score'] = None
            signals['registrar_assessment'] = 'Unable to determine registrar'
        
        return signals
    
    def get_trust_score(self, url_or_domain: str) -> Optional[float]:
        """
        Get a composite WHOIS trust score (0-10) for a domain.
        
        Returns None if WHOIS lookup fails.
        """
        result = self.lookup(url_or_domain)
        
        if 'error' in result:
            return None
        
        signals = result.get('trust_signals', {})
        
        # Weight the different signals
        scores = []
        weights = []
        
        # Domain age is most important
        if signals.get('domain_age_score') is not None:
            scores.append(signals['domain_age_score'])
            weights.append(0.4)
        
        # Privacy status
        if signals.get('privacy_score') is not None:
            scores.append(signals['privacy_score'])
            weights.append(0.2)
        
        # Expiration
        if signals.get('expiration_score') is not None:
            scores.append(signals['expiration_score'])
            weights.append(0.2)
        
        # Registrar
        if signals.get('registrar_score') is not None:
            scores.append(signals['registrar_score'])
            weights.append(0.2)
        
        if not scores:
            return None
        
        # Weighted average
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        total_weight = sum(weights)
        
        return round(weighted_sum / total_weight, 1) if total_weight > 0 else None


# Global singleton for easy access
_whois_lookup = None

def get_whois_lookup() -> WHOISLookup:
    """Get the global WHOISLookup instance."""
    global _whois_lookup
    if _whois_lookup is None:
        _whois_lookup = WHOISLookup()
    return _whois_lookup
