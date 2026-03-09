"""
Test API-based geo resolution with fallback.

Author: gadwant
"""
import pytest
from unittest.mock import patch, MagicMock

from tracemap.geo_api import (
    IPApiGeoLocator,
    IPApiCoLocator,
    ResilientAPILocator,
    HybridGeoLocator,
)
from tracemap.models import HopGeo


class TestIPApiGeoLocator:
    """Test ip-api.com locator."""

    @patch('tracemap.geo_api.urlopen')
    def test_successful_lookup(self, mock_urlopen):
        """Test successful API call."""
        # Mock response
        mock_response = MagicMock()
        mock_response.read.return_value = b'''{
            "status": "success",
            "country": "United States",
            "countryCode": "US",
            "region": "CA",
            "city": "Mountain View",
            "lat": 37.4056,
            "lon": -122.0775,
            "as": "AS15169 Google LLC"
        }'''
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        locator = IPApiGeoLocator()
        result = locator.locate("8.8.8.8")

        assert result is not None
        assert result.city == "Mountain View"
        assert result.lat == pytest.approx(37.4056)
        assert result.lon == pytest.approx(-122.0775)
        assert result.asn == 15169
        assert result.asn_org == "Google LLC"

    @patch('tracemap.geo_api.urlopen')
    def test_failed_lookup(self, mock_urlopen):
        """Test failed API call."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "fail"}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        locator = IPApiGeoLocator()
        result = locator.locate("invalid")

        assert result is None


class TestIPApiCoLocator:
    """Test ipapi.co locator."""

    @patch('tracemap.geo_api.urlopen')
    def test_successful_lookup(self, mock_urlopen):
        """Test successful API call."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'''{
            "latitude": 37.4056,
            "longitude": -122.0775,
            "city": "Mountain View",
            "region": "California",
            "country_name": "United States",
            "country_code": "US",
            "asn": "AS15169",
            "org": "Google LLC"
        }'''
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        locator = IPApiCoLocator()
        result = locator.locate("8.8.8.8")

        assert result is not None
        assert result.city == "Mountain View"
        assert result.lat == pytest.approx(37.4056)
        assert result.asn == 15169

    @patch('tracemap.geo_api.urlopen')
    def test_error_response(self, mock_urlopen):
        """Test error response."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"error": true}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        locator = IPApiCoLocator()
        result = locator.locate("invalid")

        assert result is None


class TestResilientAPILocator:
    """Test cascading fallback API locator."""

    def test_primary_success(self):
        """Test that primary API is used when working."""
        locator = ResilientAPILocator(use_cache=False)
        
        # Mock primary provider to succeed
        mock_result = HopGeo(lat=37.4, lon=-122.1, city="Test City")
        locator.providers[0] = ("ip-api.com", MagicMock(locate=MagicMock(return_value=mock_result)))
        
        result = locator.locate("8.8.8.8")
        
        assert result == mock_result
        assert locator._success_count["ip-api.com"] == 1
        assert locator._failure_count["ip-api.com"] == 0

    def test_fallback_to_secondary(self):
        """Test fallback when primary API fails."""
        locator = ResilientAPILocator(use_cache=False)
        
        # Mock primary to fail, secondary to succeed
        locator.providers[0] = ("ip-api.com", MagicMock(locate=MagicMock(return_value=None)))
        mock_result = HopGeo(lat=37.4, lon=-122.1, city="Backup City")
        locator.providers[1] = ("ipapi.co", MagicMock(locate=MagicMock(return_value=mock_result)))
        
        result = locator.locate("8.8.8.8")
        
        assert result == mock_result
        assert locator._failure_count["ip-api.com"] == 1
        assert locator._success_count["ipapi.co"] == 1

    def test_all_providers_fail(self):
        """Test when all providers fail."""
        locator = ResilientAPILocator(use_cache=False)
        
        # Mock all to fail
        locator.providers[0] = ("ip-api.com", MagicMock(locate=MagicMock(return_value=None)))
        locator.providers[1] = ("ipapi.co", MagicMock(locate=MagicMock(return_value=None)))
        
        result = locator.locate("8.8.8.8")
        
        assert result is None
        assert locator._failure_count["ip-api.com"] == 1
        assert locator._failure_count["ipapi.co"] == 1

    def test_stats_tracking(self):
        """Test statistics tracking."""
        locator = ResilientAPILocator(use_cache=False)
        
        # Mock some successes and failures
        mock_result = HopGeo(lat=37.4, lon=-122.1)
        locator.providers[0] = ("ip-api.com", MagicMock(locate=MagicMock(return_value=mock_result)))
        
        # Multiple lookups
        locator.locate("8.8.8.8")
        locator.locate("1.1.1.1")
        
        stats = locator.get_stats()
        assert stats["success"]["ip-api.com"] == 2
        assert stats["failure"]["ip-api.com"] == 0


class TestHybridGeoLocator:
    """Test hybrid geo locator with multiple sources."""

    def test_uses_local_first(self):
        """Test that local database is tried first."""
        mock_local = MagicMock()
        mock_result = HopGeo(lat=37.4, lon=-122.1, city="Local")
        mock_local.locate.return_value = mock_result
        
        mock_api = MagicMock()
        
        hybrid = HybridGeoLocator(
            local_locator=mock_local,
            api_locator=mock_api,
            fallback_to_mock=False,
        )
        
        result = hybrid.locate("8.8.8.8")
        
        assert result == mock_result
        mock_local.locate.assert_called_once_with("8.8.8.8")
        mock_api.locate.assert_not_called()

    def test_falls_back_to_api(self):
        """Test fallback to API when local fails."""
        mock_local = MagicMock()
        mock_local.locate.return_value = None
        
        mock_api = MagicMock()
        mock_result = HopGeo(lat=37.4, lon=-122.1, city="API")
        mock_api.locate.return_value = mock_result
        
        hybrid = HybridGeoLocator(
            local_locator=mock_local,
            api_locator=mock_api,
            fallback_to_mock=False,
        )
        
        result = hybrid.locate("8.8.8.8")
        
        assert result == mock_result
        assert hybrid._stats["api_hits"] == 1

    def test_stats_collection(self):
        """Test statistics collection."""
        mock_api = MagicMock()
        mock_api.locate.return_value = HopGeo(lat=37.4, lon=-122.1)
        mock_api.get_stats.return_value = {"success": {"ip-api.com": 1}}
        
        hybrid = HybridGeoLocator(
            api_locator=mock_api,
            fallback_to_mock=False,
        )
        
        hybrid.locate("8.8.8.8")
        
        stats = hybrid.get_stats()
        assert stats["total_lookups"] == 1
        assert stats["api_hits"] == 1
        assert "api_providers" in stats
