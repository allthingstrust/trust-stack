"""
SSL Utility Module for Trust Stack Analysis

Provides functions to check SSL certificate validity, expiration, and issuer information
to support the Source Domain Trust Baseline signal.
"""

import ssl
import socket
import logging
from urllib.parse import urlparse
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def get_ssl_data(url: str, timeout: int = 5) -> Dict[str, Any]:
    """
    Connect to a URL's host and extract SSL certificate information.

    Args:
        url: The URL to check (must be reachable)
        timeout: Socket timeout in seconds

    Returns:
        Dict with keys:
            - ssl_valid (str): "true" or "false" (string format for meta dict)
            - ssl_issuer (str): Issuer organization or common name
            - ssl_expiry_days (int): Days until expiration
            - ssl_error (str): Error message if validation failed
    """
    result = {
        "ssl_valid": "false",
        "ssl_issuer": "",
        "ssl_expiry_days": None,
        "ssl_error": ""
    }

    try:
        parsed = urlparse(url)
        hostname = parsed.netloc.split(':')[0] # Remove port if present
        
        # Skip if not https (though we might want to check port 443 anyway, 
        # usually we only care if the content itself was served securely)
        if parsed.scheme != 'https':
            result["ssl_error"] = "Not HTTPS"
            return result

        context = ssl.create_default_context()
        try:
            import certifi
            context.load_verify_locations(cafile=certifi.where())
        except ImportError:
            pass # Fallback to system default if certifi missing
        
        with socket.create_connection((hostname, 443), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                
                # If we got here without exception, the cert is valid for the hostname
                result["ssl_valid"] = "true"
                
                # Extract expiration
                not_after_str = cert.get('notAfter')
                if not_after_str:
                    # Format: 'May 20 12:00:00 2026 GMT'
                    ssl_date_fmt = r'%b %d %H:%M:%S %Y %Z'
                    expiry_date = datetime.strptime(not_after_str, ssl_date_fmt)
                    days_left = (expiry_date - datetime.utcnow()).days
                    result["ssl_expiry_days"] = days_left
                
                # Extract Issuer
                # cert['issuer'] is a tuple of tuples, e.g.:
                # ((('countryName', 'US'),), (('organizationName', 'Google Trust Services LLC'),), (('commonName', 'GTS CA 1C3'),))
                issuer_dict = {key: value for rdn in cert.get('issuer', []) for key, value in rdn}
                result["ssl_issuer"] = issuer_dict.get('organizationName') or issuer_dict.get('commonName') or "Unknown"

    except ssl.SSLCertVerificationError as e:
        result["ssl_valid"] = "false"
        result["ssl_error"] = f"Certificate verification failed: {e.verify_message}"
        logger.debug(f"SSL verification failed for {url}: {e}")
    except ssl.SSLError as e:
        result["ssl_valid"] = "false"
        result["ssl_error"] = f"SSL protocol error: {e}"
        logger.debug(f"SSL error for {url}: {e}")
    except socket.timeout:
        result["ssl_valid"] = "false" # Timeout implies we can't verify
        result["ssl_error"] = "Connection timed out"
    except Exception as e:
        result["ssl_valid"] = "false"
        result["ssl_error"] = str(e)
        logger.debug(f"Error checking SSL for {url}: {e}")

    return result
