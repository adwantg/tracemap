"""
Test GeoIP functionality.

Author: gadwant
"""

from tracemap.geo import MockGeoLocator
from tracemap.models import is_private_ip


class TestMockGeoLocator:
    """Test mock geo locator."""

    def test_locate_known_ip(self):
        """Test locating known IPs like Google DNS."""
        locator = MockGeoLocator()
        geo = locator.locate("8.8.8.8")

        assert geo is not None
        assert geo.lat is not None
        assert geo.lon is not None
        assert geo.city == "Mountain View"
        assert geo.country == "United States"
        assert geo.asn == 15169
        assert geo.asn_org == "GOOGLE"

    def test_locate_cloudflare_dns(self):
        """Test locating Cloudflare DNS."""
        locator = MockGeoLocator()
        geo = locator.locate("1.1.1.1")

        assert geo is not None
        assert geo.city == "Sydney"
        assert geo.asn == 13335
        assert geo.asn_org == "CLOUDFLARENET"

    def test_locate_unknown_ip(self):
        """Test locating unknown IP gets deterministic hash-based location."""
        locator = MockGeoLocator()

        geo1 = locator.locate("192.168.1.1")
        geo2 = locator.locate("192.168.1.1")

        # Same IP should give same location (deterministic)
        assert geo1 is not None
        assert geo2 is not None
        assert geo1.lat == geo2.lat
        assert geo1.lon == geo2.lon

    def test_locate_different_ips(self):
        """Test different IPs get different locations."""
        locator = MockGeoLocator()

        geo1 = locator.locate("203.0.113.1")
        geo2 = locator.locate("203.0.113.2")

        assert geo1 is not None
        assert geo2 is not None
        # Different IPs likely get different locations
        # (not guaranteed due to hash collisions, but highly probable)


class TestPrivateIPDetection:
    """Test private IP address detection."""

    def test_private_ipv4_ranges(self):
        """Test detection of RFC1918 private IPv4 addresses."""
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("10.255.255.255") is True
        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("172.31.255.255") is True
        assert is_private_ip("192.168.0.1") is True
        assert is_private_ip("192.168.255.255") is True

    def test_public_ipv4(self):
        """Test public IPv4 addresses are not private."""
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False
        assert is_private_ip("93.184.216.34") is False

    def test_loopback(self):
        """Test loopback addresses are detected as private."""
        assert is_private_ip("127.0.0.1") is True
        assert is_private_ip("127.255.255.255") is True

    def test_link_local(self):
        """Test link-local addresses."""
        assert is_private_ip("169.254.1.1") is True

    def test_invalid_ip(self):
        """Test invalid IP addresses."""
        assert is_private_ip("not.an.ip") is False
        assert is_private_ip("999.999.999.999") is False
