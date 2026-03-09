"""
GeoIP resolution with pluggable backends.

Provides:
- MockGeoLocator: Deterministic fake geo for development
- MaxMindGeoLocator: Local MaxMind GeoLite2 database
- EnhancedGeoLocator: Combines GeoIP with ASN lookups

Author: gadwant
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Protocol

from .models import HopGeo


class GeoLocator(Protocol):
    """Protocol for geo locators."""

    def locate(self, ip: str) -> Optional[HopGeo]:
        """Locate an IP address and return geographic information."""
        ...


class MockGeoLocator:
    """
    Deterministic fake GeoIP for development and demos.

    It hashes the IP to a (lat, lon) so the same IP is always in the same place,
    producing stable traces for renderer iteration.
    """

    # Some well-known IPs with realistic locations for demos
    KNOWN_IPS = {
        "8.8.8.8": HopGeo(
            lat=37.4056,
            lon=-122.0775,
            city="Mountain View",
            country="United States",
            country_code="US",
            asn=15169,
            asn_org="GOOGLE",
        ),
        "8.8.4.4": HopGeo(
            lat=37.4056,
            lon=-122.0775,
            city="Mountain View",
            country="United States",
            country_code="US",
            asn=15169,
            asn_org="GOOGLE",
        ),
        "1.1.1.1": HopGeo(
            lat=-33.8688,
            lon=151.2093,
            city="Sydney",
            country="Australia",
            country_code="AU",
            asn=13335,
            asn_org="CLOUDFLARENET",
        ),
        "1.0.0.1": HopGeo(
            lat=-33.8688,
            lon=151.2093,
            city="Sydney",
            country="Australia",
            country_code="AU",
            asn=13335,
            asn_org="CLOUDFLARENET",
        ),
        "208.67.222.222": HopGeo(
            lat=37.7749,
            lon=-122.4194,
            city="San Francisco",
            country="United States",
            country_code="US",
            asn=36692,
            asn_org="OPENDNS",
        ),
        "9.9.9.9": HopGeo(
            lat=47.6062,
            lon=-122.3321,
            city="Seattle",
            country="United States",
            country_code="US",
            asn=19281,
            asn_org="QUAD9",
        ),
    }

    # Major internet exchange/hub cities for more realistic routing
    HUB_CITIES = [
        (40.7128, -74.0060, "New York", "US"),  # NYC
        (51.5074, -0.1278, "London", "GB"),  # London
        (52.5200, 13.4050, "Berlin", "DE"),  # Berlin
        (48.8566, 2.3522, "Paris", "FR"),  # Paris
        (35.6762, 139.6503, "Tokyo", "JP"),  # Tokyo
        (37.5665, 126.9780, "Seoul", "KR"),  # Seoul
        (22.3193, 114.1694, "Hong Kong", "HK"),  # Hong Kong
        (1.3521, 103.8198, "Singapore", "SG"),  # Singapore
        (-33.8688, 151.2093, "Sydney", "AU"),  # Sydney
        (37.7749, -122.4194, "San Francisco", "US"),  # SF
        (47.6062, -122.3321, "Seattle", "US"),  # Seattle
        (33.7490, -84.3880, "Atlanta", "US"),  # Atlanta
        (41.8781, -87.6298, "Chicago", "US"),  # Chicago
        (25.7617, -80.1918, "Miami", "US"),  # Miami
        (55.7558, 37.6173, "Moscow", "RU"),  # Moscow
        (-23.5505, -46.6333, "São Paulo", "BR"),  # São Paulo
    ]

    def locate(self, ip: str) -> Optional[HopGeo]:
        """Locate an IP with deterministic mock data."""
        # Check known IPs first
        if ip in self.KNOWN_IPS:
            return self.KNOWN_IPS[ip]

        # Hash-based deterministic location
        h = hashlib.sha256(ip.encode("utf-8")).digest()

        # Use hash to pick a hub city (more realistic than random coords)
        city_idx = int.from_bytes(h[0:2], "big") % len(self.HUB_CITIES)
        lat, lon, city, country_code = self.HUB_CITIES[city_idx]

        # Add small random offset for variety
        lat_offset = (int.from_bytes(h[2:4], "big") / 65535.0 - 0.5) * 5
        lon_offset = (int.from_bytes(h[4:6], "big") / 65535.0 - 0.5) * 5

        # Generate fake ASN from hash
        asn = (int.from_bytes(h[6:8], "big") % 60000) + 1000

        return HopGeo(
            lat=lat + lat_offset,
            lon=lon + lon_offset,
            city=city,
            country=f"Mock-{country_code}",
            country_code=country_code,
            asn=asn,
            asn_org=f"MOCK-AS{asn}",
        )


class MaxMindGeoLocator:
    """
    GeoIP resolver backed by a local MaxMind GeoLite2 City mmdb.

    Requires optional dependency: maxminddb

    Usage:
        locator = MaxMindGeoLocator(Path("/path/to/GeoLite2-City.mmdb"))
        geo = locator.locate("8.8.8.8")
    """

    def __init__(self, mmdb_path: Path):
        """
        Initialize with path to MaxMind database.

        Args:
            mmdb_path: Path to GeoLite2-City.mmdb file
        """
        import maxminddb  # type: ignore

        self.mmdb_path = mmdb_path
        self.reader = maxminddb.open_database(str(mmdb_path))

    def locate(self, ip: str) -> Optional[HopGeo]:
        """Look up geographic information for an IP."""
        rec = self.reader.get(ip)
        if not rec:
            return None

        loc = rec.get("location") or {}
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if lat is None or lon is None:
            return None

        city = ((rec.get("city") or {}).get("names") or {}).get("en")
        country = ((rec.get("country") or {}).get("names") or {}).get("en")
        country_code = (rec.get("country") or {}).get("iso_code")

        region = None
        subs = rec.get("subdivisions") or []
        if subs:
            region = (subs[0].get("names") or {}).get("en")

        return HopGeo(
            lat=float(lat),
            lon=float(lon),
            city=city,
            country=country,
            country_code=country_code,
            region=region,
        )

    def close(self) -> None:
        """Close the database reader."""
        self.reader.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class EnhancedGeoLocator:
    """
    Enhanced geo locator that combines GeoIP with ASN lookups.

    Wraps a base GeoLocator and adds ASN information from an ASN resolver.
    """

    def __init__(
        self,
        geo_locator: GeoLocator,
        asn_resolver=None,
    ):
        """
        Initialize with geo locator and optional ASN resolver.

        Args:
            geo_locator: Base geo locator (MaxMind or Mock)
            asn_resolver: Optional ASN resolver for enrichment
        """
        self.geo_locator = geo_locator
        self.asn_resolver = asn_resolver

    def locate(self, ip: str) -> Optional[HopGeo]:
        """Locate with geo and ASN enrichment."""
        geo = self.geo_locator.locate(ip)

        if geo and self.asn_resolver:
            try:
                asn_info = self.asn_resolver.lookup(ip)
                if asn_info:
                    geo.asn = asn_info.asn
                    geo.asn_org = asn_info.org
                    # Use ASN country if geo country is missing
                    if not geo.country_code and asn_info.country:
                        geo.country_code = asn_info.country
            except Exception:
                pass

        return geo


class CachingGeoLocator:
    """
    Geo locator with LRU caching.

    Wraps any GeoLocator and caches results.
    """

    def __init__(self, locator: GeoLocator, maxsize: int = 10000):
        """
        Initialize with a base locator.

        Args:
            locator: The underlying geo locator
            maxsize: Maximum cache size
        """
        self._locator = locator
        self._cache: dict[str, Optional[HopGeo]] = {}
        self._maxsize = maxsize

    def locate(self, ip: str) -> Optional[HopGeo]:
        """Look up with caching."""
        if ip in self._cache:
            return self._cache[ip]

        # Evict if at capacity
        if len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

        result = self._locator.locate(ip)
        self._cache[ip] = result
        return result

    def cache_clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()

    def cache_stats(self) -> dict:
        """Return cache statistics."""
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
        }
