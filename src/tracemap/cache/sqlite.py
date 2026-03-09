"""
SQLite-based persistent cache for geo/ASN/DNS lookups.

Stores results with TTLs to balance freshness vs API usage:
- GeoIP: 30 days (locations rarely change)
- ASN: 90 days (very stable)
- DNS/PTR: 24 hours (more dynamic)

Author: gadwant
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..models import HopGeo


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    expired: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class GeoCache:
    """
    Persistent cache for GeoIP lookups.

    Stores geo location data with source attribution and confidence scoring.
    """

    DEFAULT_TTL_DAYS = 30

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize geo cache.

        Args:
            db_path: Path to SQLite database (default: ~/.tracemap/cache.sqlite)
        """
        if db_path is None:
            cache_dir = Path.home() / ".tracemap"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = cache_dir / "cache.sqlite"

        self.db_path = db_path
        self.stats = CacheStats()
        self._init_schema()

    def _init_schema(self):
        """Create cache tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS geo_cache (
                    ip TEXT PRIMARY KEY,
                    lat REAL,
                    lon REAL,
                    city TEXT,
                    country TEXT,
                    country_code TEXT,
                    asn INTEGER,
                    asn_org TEXT,
                    source TEXT,
                    confidence TEXT,
                    cached_at INTEGER,
                    expires_at INTEGER
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_geo_expires
                ON geo_cache(expires_at)
            """)

    def get(self, ip: str) -> Optional[HopGeo]:
        """
        Retrieve cached geo data for IP.

        Args:
            ip: IP address to look up

        Returns:
            HopGeo if cached and not expired, None otherwise
        """
        now = int(time.time())

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM geo_cache
                WHERE ip = ? AND expires_at > ?
                """,
                (ip, now),
            )
            row = cursor.fetchone()

            if row:
                self.stats.hits += 1
                return HopGeo(
                    lat=row["lat"],
                    lon=row["lon"],
                    city=row["city"],
                    country=row["country"],
                    country_code=row["country_code"],
                    asn=row["asn"],
                    asn_org=row["asn_org"],
                )

            # Check if expired entry exists
            cursor = conn.execute(
                "SELECT 1 FROM geo_cache WHERE ip = ? AND expires_at <= ?", (ip, now)
            )
            if cursor.fetchone():
                self.stats.expired += 1
            else:
                self.stats.misses += 1

            return None

    def set(
        self,
        ip: str,
        geo: HopGeo,
        source: str,
        confidence: str = "medium",
        ttl_days: int = DEFAULT_TTL_DAYS,
    ):
        """
        Store geo data in cache.

        Args:
            ip: IP address
            geo: Geographic data
            source: Data source (e.g., 'ip-api', 'ipapi', 'mmdb', 'mock')
            confidence: Confidence level ('high', 'medium', 'low')
            ttl_days: Time to live in days
        """
        now = int(time.time())
        expires_at = now + (ttl_days * 86400)  # days to seconds

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO geo_cache
                (ip, lat, lon, city, country, country_code, asn, asn_org,
                 source, confidence, cached_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ip,
                    geo.lat,
                    geo.lon,
                    geo.city,
                    geo.country,
                    geo.country_code,
                    geo.asn,
                    geo.asn_org,
                    source,
                    confidence,
                    now,
                    expires_at,
                ),
            )

    def clear_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM geo_cache WHERE expires_at <= ?", (now,))
            return cursor.rowcount

    def clear_all(self):
        """Clear all cached geo data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM geo_cache")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM geo_cache")
            total_entries = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT COUNT(*) FROM geo_cache WHERE expires_at > ?", (int(time.time()),)
            )
            valid_entries = cursor.fetchone()[0]

        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "expired_entries": total_entries - valid_entries,
            "hit_rate": self.stats.hit_rate,
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "expired_lookups": self.stats.expired,
        }


class ASNCache:
    """Persistent cache for ASN lookups."""

    DEFAULT_TTL_DAYS = 90  # ASN data is very stable

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            cache_dir = Path.home() / ".tracemap"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = cache_dir / "cache.sqlite"

        self.db_path = db_path
        self.stats = CacheStats()
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS asn_cache (
                    ip TEXT PRIMARY KEY,
                    asn INTEGER,
                    asn_org TEXT,
                    cached_at INTEGER,
                    expires_at INTEGER
                )
            """)

    def get(self, ip: str) -> Optional[tuple[int, str]]:
        """Get cached ASN data. Returns (asn, org) or None."""
        now = int(time.time())

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT asn, asn_org FROM asn_cache WHERE ip = ? AND expires_at > ?", (ip, now)
            )
            row = cursor.fetchone()

            if row:
                self.stats.hits += 1
                return (row["asn"], row["asn_org"])

            self.stats.misses += 1
            return None

    def set(self, ip: str, asn: int, asn_org: str, ttl_days: int = DEFAULT_TTL_DAYS):
        """Store ASN data in cache."""
        now = int(time.time())
        expires_at = now + (ttl_days * 86400)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO asn_cache
                (ip, asn, asn_org, cached_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ip, asn, asn_org, now, expires_at),
            )


class DNSCache:
    """Persistent cache for reverse DNS (PTR) lookups."""

    DEFAULT_TTL_HOURS = 24  # DNS is more dynamic

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            cache_dir = Path.home() / ".tracemap"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = cache_dir / "cache.sqlite"

        self.db_path = db_path
        self.stats = CacheStats()
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dns_cache (
                    ip TEXT PRIMARY KEY,
                    hostname TEXT,
                    cached_at INTEGER,
                    expires_at INTEGER
                )
            """)

    def get(self, ip: str) -> Optional[str]:
        """Get cached hostname for IP."""
        now = int(time.time())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT hostname FROM dns_cache WHERE ip = ? AND expires_at > ?", (ip, now)
            )
            row = cursor.fetchone()

            if row:
                self.stats.hits += 1
                return row[0]

            self.stats.misses += 1
            return None

    def set(self, ip: str, hostname: str, ttl_hours: int = DEFAULT_TTL_HOURS):
        """Store hostname in cache."""
        now = int(time.time())
        expires_at = now + (ttl_hours * 3600)  # hours to seconds

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dns_cache
                (ip, hostname, cached_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (ip, hostname, now, expires_at),
            )
