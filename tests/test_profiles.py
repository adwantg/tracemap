"""
Test suite for profiles module.

Tests privacy and offline profile configurations.

Author: gadwant
"""

import pytest

from tracemap.profiles import get_profile, list_profiles


class TestProfiles:
    """Test profile configurations."""

    def test_get_default_profile(self):
        """Test default profile."""
        profile = get_profile("default")
        assert profile.name == "default"
        assert profile.use_api is True
        assert profile.use_dns is True
        assert profile.redact_ips is False

    def test_get_offline_profile(self):
        """Test offline profile."""
        profile = get_profile("offline")
        assert profile.name == "offline"
        assert profile.use_api is False
        assert profile.require_mmdb is True

    def test_get_private_profile(self):
        """Test private profile."""
        profile = get_profile("private")
        assert profile.name == "private"
        assert profile.use_api is False
        assert profile.use_dns is False
        assert profile.redact_ips is True
        assert profile.redact_hostnames is True

    def test_get_fast_profile(self):
        """Test fast profile."""
        profile = get_profile("fast")
        assert profile.name == "fast"
        assert profile.use_api is True
        assert profile.use_dns is False  # Skip slow DNS

    def test_unknown_profile(self):
        """Test unknown profile raises error."""
        with pytest.raises(ValueError, match="Unknown profile"):
            get_profile("nonexistent")

    def test_list_profiles(self):
        """Test listing all profiles."""
        profiles = list_profiles()
        assert len(profiles) == 4
        names = [p.name for p in profiles]
        assert "default" in names
        assert "offline" in names
        assert "private" in names
        assert "fast" in names

    def test_offline_validation_without_mmdb(self):
        """Test offline profile validation fails without MMDB."""
        profile = get_profile("offline")
        is_valid, error = profile.validate(mmdb_path=None)
        assert is_valid is False
        assert "requires local MMDB" in error

    def test_offline_validation_with_mmdb(self):
        """Test offline profile validation succeeds with MMDB."""
        profile = get_profile("offline")
        is_valid, error = profile.validate(mmdb_path="/path/to/db.mmdb")
        assert is_valid is True
        assert error is None

    def test_private_profile_no_requirements(self):
        """Test private profile works without MMDB."""
        profile = get_profile("private")
        is_valid, error = profile.validate(mmdb_path=None)
        assert is_valid is True
