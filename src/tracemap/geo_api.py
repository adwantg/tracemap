"""
API-based GeoIP resolver using free public APIs.

Provides real-time geo lookups without requiring local databases.

Author: gadwant
"""
from __future__ import annotations

import time
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError
import json

from .models import HopGeo


class IPApiGeoLocator:
    """
    GeoIP resolver using ip-api.com free API.
    
    Features:
    - No API key required
    - 45 requests/minute free tier
    - Includes latitude, longitude, city, country, ASN
    - High accuracy for most IPs
    
    Rate Limits:
    - Free: 45 requests/minute
    - Pro: unlimited (requires API key)
    """

    def __init__(self, timeout: float = 3.0):
        """
        Initialize API-based geo locator.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.base_url = "http://ip-api.com/json"
        self._last_request_time = 0.0
        self._min_request_interval = 1.0 / 45  # 45 requests/minute = ~1.3s between requests
        
    def locate(self, ip: str) -> Optional[HopGeo]:
        """
        Look up geographic information for an IP using ip-api.com.
        
        Args:
            ip: IP address to locate
            
        Returns:
            HopGeo with location data, or None if lookup fails
        """
        # Rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        
        try:
            # Build URL with fields we need
            fields = "status,message,country,countryCode,region,city,lat,lon,as,asname"
            url = f"{self.base_url}/{ip}?fields={fields}"
            
            # Make request
            with urlopen(url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            self._last_request_time = time.time()
            
            # Check if successful
            if data.get('status') != 'success':
                return None
            
            # Parse ASN (format: "AS15169 Google LLC")
            asn_str = data.get('as', '')
            asn = None
            asn_org = None
            if asn_str:
                parts = asn_str.split(' ', 1)
                if parts[0].startswith('AS'):
                    try:
                        asn = int(parts[0][2:])
                        asn_org = parts[1] if len(parts) > 1 else None
                    except ValueError:
                        pass
            
            return HopGeo(
                lat=float(data['lat']),
                lon=float(data['lon']),
                city=data.get('city'),
                country=data.get('country'),
                country_code=data.get('countryCode'),
                region=data.get('region'),
                asn=asn,
                asn_org=asn_org,
            )
            
        except (URLError, json.JSONDecodeError, KeyError, ValueError, TimeoutError):
            return None


class IPApiCoLocator:
    """
    GeoIP resolver using ipapi.co free API.
    
    Features:
    - No API key required for free tier
    - 1000 requests/day, 30,000/month free
    - Includes latitude, longitude, city, country, ASN
    - Good fallback option for ip-api.com
    """

    def __init__(self, timeout: float = 3.0):
        """
        Initialize ipapi.co geo locator.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.base_url = "https://ipapi.co"
        
    def locate(self, ip: str) -> Optional[HopGeo]:
        """
        Look up geographic information using ipapi.co.
        
        Args:
            ip: IP address to locate
            
        Returns:
            HopGeo with location data, or None if lookup fails
        """
        try:
            url = f"{self.base_url}/{ip}/json/"
            
            with urlopen(url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            # Check for error
            if 'error' in data or not data.get('latitude'):
                return None
            
            # Parse ASN (format: "AS15169")
            asn_str = data.get('asn', '')
            asn = None
            asn_org = data.get('org')
            
            if asn_str and asn_str.startswith('AS'):
                try:
                    asn = int(asn_str[2:])
                except ValueError:
                    pass
            
            return HopGeo(
                lat=float(data['latitude']),
                lon=float(data['longitude']),
                city=data.get('city'),
                country=data.get('country_name'),
                country_code=data.get('country_code'),
                region=data.get('region'),
                asn=asn,
                asn_org=asn_org,
            )
            
        except (URLError, json.JSONDecodeError, KeyError, ValueError, TimeoutError):
            return None


class IPInfoGeoLocator:
    """
    GeoIP resolver using ipinfo.io API.
    
    Features:
    - High accuracy
    - Includes ASN data
    - 50k requests/month free tier with API key
    - Fallback to limited free tier without key
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 3.0):
        """
        Initialize ipinfo.io geo locator.
        
        Args:
            api_key: Optional API key for higher limits
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://ipinfo.io"
        
    def locate(self, ip: str) -> Optional[HopGeo]:
        """Look up geographic information using ipinfo.io."""
        try:
            url = f"{self.base_url}/{ip}/json"
            if self.api_key:
                url += f"?token={self.api_key}"
            
            with urlopen(url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            # Parse location (format: "lat,lon")
            loc = data.get('loc', '')
            if not loc or ',' not in loc:
                return None
            
            lat_str, lon_str = loc.split(',')
            lat = float(lat_str)
            lon = float(lon_str)
            
            # Parse ASN (separate query or from org field)
            asn = None
            asn_org = data.get('org')
            if asn_org and asn_org.startswith('AS'):
                parts = asn_org.split(' ', 1)
                try:
                    asn = int(parts[0][2:])
                    asn_org = parts[1] if len(parts) > 1 else None
                except ValueError:
                    pass
            
            return HopGeo(
                lat=lat,
                lon=lon,
                city=data.get('city'),
                country=data.get('country'),
                country_code=data.get('country'),  # ipinfo uses 2-letter codes
                region=data.get('region'),
                asn=asn,
                asn_org=asn_org,
            )
            
        except (URLError, json.JSONDecodeError, KeyError, ValueError, TimeoutError):
            return None


class ResilientAPILocator:
    """
    Resilient API-based geo locator with cascading fallback.
    
    Tries multiple API providers in order:
    1. ip-api.com (45/min, no key, fast)
    2. ipapi.co (1000/day, no key, HTTPS)
    3. Returns None if all fail
    
    This provides high reliability even if one service is down.
    """

    def __init__(self, timeout: float = 3.0, verbose: bool = False, use_cache: bool = True):
        """
        Initialize resilient API locator.
        
        Args:
            timeout: Request timeout in seconds
            verbose: Whether to print fallback messages
            use_cache: Whether to use persistent caching
        """
        self.timeout = timeout
        self.verbose = verbose
        self.use_cache = use_cache
        
        # Initialize cache if enabled
        if use_cache:
            from .cache import GeoCache
            self.cache = GeoCache()
        else:
            self.cache = None
        
        # Initialize all API providers
        self.providers = [
            ("ip-api.com", IPApiGeoLocator(timeout=timeout)),
            ("ipapi.co", IPApiCoLocator(timeout=timeout)),
        ]
        
        # Track which provider is working best
        self._success_count = {name: 0 for name, _ in self.providers}
        self._failure_count = {name: 0 for name, _ in self.providers}
    
    def locate(self, ip: str) -> Optional[HopGeo]:
        """
        Look up IP using cache first, then multiple APIs with fallback.
        
        Args:
            ip: IP address to locate
            
        Returns:
            HopGeo with location data, or None if all sources fail
        """
        # Check cache first
        if self.cache:
            cached_result = self.cache.get(ip)
            if cached_result:
                if self.verbose:
                    print(f"  ✅ Cache hit for {ip}")
                return cached_result
        
        last_error = None
        
        # Try API providers
        for provider_name, provider in self.providers:
            try:
                result = provider.locate(ip)
                
                if result:
                    self._success_count[provider_name] += 1
                    if self.verbose and provider_name != self.providers[0][0]:
                        print(f"  Using {provider_name} (fallback)")
                    
                    # Store in cache
                    if self.cache:
                        # Determine confidence based on provider
                        confidence = "high" if provider_name == "ip-api.com" else "medium"
                        self.cache.set(ip, result, source=provider_name, confidence=confidence)
                    
                    return result
                else:
                    self._failure_count[provider_name] += 1
                    
            except Exception as e:
                self._failure_count[provider_name] += 1
                last_error = e
                if self.verbose:
                    print(f"  {provider_name} failed: {e}")
                continue
        
        # All providers failed
        return None
    
    def get_stats(self) -> dict:
        """Get statistics about API provider reliability."""
        return {
            "success": self._success_count.copy(),
            "failure": self._failure_count.copy(),
        }


class HybridGeoLocator:
    """
    Hybrid geo locator that tries multiple sources in order:
    
    1. Local database (if configured) - fastest
    2. Resilient API lookup (ip-api.com → ipapi.co) - accurate
    3. Fallback to mock data - always works
    
    This provides the best balance of speed, accuracy, and reliability.
    """

    def __init__(
        self,
        local_locator: Optional[object] = None,
        api_locator: Optional[object] = None,
        fallback_to_mock: bool = True,
        verbose: bool = False,
    ):
        """
        Initialize hybrid geo locator.
        
        Args:
            local_locator: Optional local database locator (MaxMind, etc.)
            api_locator: Optional API locator (ResilientAPILocator, etc.)
            fallback_to_mock: Whether to use mock data as last resort
            verbose: Whether to print debug messages
        """
        self.local_locator = local_locator
        self.api_locator = api_locator or ResilientAPILocator(verbose=verbose)
        self.fallback_to_mock = fallback_to_mock
        self.verbose = verbose
        
        if fallback_to_mock:
            from .geo import MockGeoLocator
            self.mock_locator = MockGeoLocator()
        else:
            self.mock_locator = None
        
        # Track stats
        self._stats = {
            "local_hits": 0,
            "api_hits": 0,
            "mock_hits": 0,
            "total_lookups": 0,
        }
    
    def locate(self, ip: str) -> Optional[HopGeo]:
        """Look up IP using multiple sources in priority order."""
        self._stats["total_lookups"] += 1
        
        # Try local database first (fastest)
        if self.local_locator:
            try:
                result = self.local_locator.locate(ip)
                if result:
                    self._stats["local_hits"] += 1
                    return result
            except Exception as e:
                if self.verbose:
                    print(f"  Local database error: {e}")
        
        # Try API lookup (accurate)
        if self.api_locator:
            try:
                result = self.api_locator.locate(ip)
                if result:
                    self._stats["api_hits"] += 1
                    return result
            except Exception as e:
                if self.verbose:
                    print(f"  API lookup error: {e}")
        
        # Fallback to mock (always works)
        if self.mock_locator:
            self._stats["mock_hits"] += 1
            return self.mock_locator.locate(ip)
        
        return None
    
    def get_stats(self) -> dict:
        """Get statistics about geo lookup performance."""
        stats = self._stats.copy()
        
        # Add API provider stats if available
        if hasattr(self.api_locator, 'get_stats'):
            stats["api_providers"] = self.api_locator.get_stats()
        
        return stats


def get_best_locator(
    mmdb_path: Optional[str] = None,
    api_key: Optional[str] = None,
    prefer_api: bool = True,
    verbose: bool = False,
) -> object:
    """
    Get the best available geo locator based on configuration.
    
    Uses cascading fallback strategy:
    1. ip-api.com (primary API, 45/min free)
    2. ipapi.co (backup API, 1000/day free)
    3. Local MaxMind database (if configured)
    4. Mock data (last resort)
    
    Args:
        mmdb_path: Path to MaxMind MMDB file (optional)
        api_key: API key for premium services (optional)
        prefer_api: Whether to prefer API over local database
        verbose: Whether to print fallback messages
        
    Returns:
        Best available geo locator with resilience
    """
    from pathlib import Path
    
    local_locator = None
    
    # Try to load local database
    if mmdb_path and Path(mmdb_path).exists():
        try:
            from .geo import MaxMindGeoLocator
            local_locator = MaxMindGeoLocator(Path(mmdb_path))
        except Exception:
            pass
    
    # Create resilient API locator with cascading fallback
    api_locator = ResilientAPILocator(timeout=3.0, verbose=verbose)
    
    # Build hybrid locator
    return HybridGeoLocator(
        local_locator=local_locator if not prefer_api else None,
        api_locator=api_locator,
        fallback_to_mock=True,
        verbose=verbose,
    )
