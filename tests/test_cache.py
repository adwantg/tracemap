"""
Test suite for cache module.

Tests persistent caching, TTLs, statistics tracking.

Author: gadwant
"""
import pytest
import time
from pathlib import Path
import tempfile

from tracemap.cache import GeoCache, ASNCache, DNSCache
from tracemap.models import HopGeo


class TestGeoCache:
    """Test GeoIP caching."""
    
    def test_cache_miss(self, tmp_path):
        """Test cache miss returns None."""
        cache = GeoCache(tmp_path / "test.sqlite")
        result = cache.get("8.8.8.8")
        assert result is None
        assert cache.stats.misses == 1
        assert cache.stats.hits == 0
    
    def test_cache_hit(self, tmp_path):
        """Test cache hit returns stored data."""
        cache = GeoCache(tmp_path / "test.sqlite")
        
        geo = HopGeo(lat=37.4, lon=-122.1, city="Mountain View")
        cache.set("8.8.8.8", geo, source="test", confidence="high")
        
        result = cache.get("8.8.8.8")
        assert result is not None
        assert result.city == "Mountain View"
        assert cache.stats.hits == 1
    
    def test_cache_expiry(self, tmp_path):
        """Test entries expire after TTL."""
        cache = GeoCache(tmp_path / "test.sqlite")
        
        geo = HopGeo(lat=37.4, lon=-122.1, city="Test")
        # Set with very short TTL (convert to days)
        cache.set("8.8.8.8", geo, source="test", ttl_days=0.00001)  # ~1 second
        
        # Should be cached initially
        assert cache.get("8.8.8.8") is not None
        
        # Wait for expiry
        time.sleep(2)
        
        # Should be expired now
        assert cache.get("8.8.8.8") is None
        assert cache.stats.expired == 1
    
    def test_cache_statistics(self, tmp_path):
        """Test statistics tracking."""
        cache = GeoCache(tmp_path / "test.sqlite")
        
        geo = HopGeo(lat=37.4, lon=-122.1, city="Test")
        cache.set("1.1.1.1", geo, source="test")
        cache.set("8.8.8.8", geo, source="test")
        
        # Hit
        cache.get("1.1.1.1")
        # Miss
        cache.get("9.9.9.9")
        
        stats = cache.get_stats()
        assert stats["total_entries"] == 2
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
    
    def test_clear_all(self, tmp_path):
        """Test clearing cache."""
        cache = GeoCache(tmp_path / "test.sqlite")
        
        geo = HopGeo(lat=37.4, lon=-122.1)
        cache.set("1.1.1.1", geo, source="test")
        cache.set("8.8.8.8", geo, source="test")
        
        cache.clear_all()
        
        stats = cache.get_stats()
        assert stats["total_entries"] == 0


class TestASNCache:
    """Test ASN caching."""
    
    def test_asn_cache(self, tmp_path):
        """Test ASN cache operations."""
        cache = ASNCache(tmp_path / "test.sqlite")
        
        # Miss
        assert cache.get("8.8.8.8") is None
        
        # Set
        cache.set("8.8.8.8", asn=15169, asn_org="Google LLC")
        
        # Hit
        result = cache.get("8.8.8.8")
        assert result == (15169, "Google LLC")


class TestDNSCache:
    """Test DNS caching."""
    
    def test_dns_cache(self, tmp_path):
        """Test DNS cache operations."""
        cache = DNSCache(tmp_path / "test.sqlite")
        
        # Miss
        assert cache.get("8.8.8.8") is None
        
        # Set
        cache.set("8.8.8.8", hostname="dns.google")
        
        # Hit
        result = cache.get("8.8.8.8")
        assert result == "dns.google"
    
    def test_dns_expiry(self, tmp_path):
        """Test DNS entries expire quickly (24h default)."""
        cache = DNSCache(tmp_path / "test.sqlite")
        
        # Short TTL for testing
        cache.set("8.8.8.8", hostname="test.com", ttl_hours=0.0003)  # ~1 second
        
        assert cache.get("8.8.8.8") == "test.com"
        
        time.sleep(2)
        
        assert cache.get("8.8.8.8") is None
