"""
Profile configurations for different use cases.

Profiles control privacy, data sources, and behavior:
- default: API-enabled, DNS enabled, caching enabled
- offline: No API calls, local MMDB only, full privacy
- private: No external lookups, aggressive redaction

Author: gadwant
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Profile:
    """Configuration profile for tracemap."""

    name: str
    description: str

    # Network settings
    use_api: bool = True
    use_dns: bool = True
    use_cache: bool = True

    # Privacy settings
    redact_ips: bool = False
    redact_hostnames: bool = False

    # Requirements
    require_mmdb: bool = False  # Fail if no local MMDB available

    def validate(self, mmdb_path: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        Validate profile requirements.

        Returns:
            (is_valid, error_message)
        """
        if self.require_mmdb and not mmdb_path:
            return False, f"Profile '{self.name}' requires local MMDB database (use --geoip-mmdb)"

        if not self.use_api and not mmdb_path and not self.redact_ips:
            return False, f"Profile '{self.name}' has no geo data source available"

        return True, None


# Predefined profiles
PROFILES = {
    "default": Profile(
        name="default",
        description="Balanced mode with API + caching (recommended)",
        use_api=True,
        use_dns=True,
        use_cache=True,
        redact_ips=False,
        redact_hostnames=False,
    ),
    "offline": Profile(
        name="offline",
        description="Completely offline using local MMDB only",
        use_api=False,
        use_dns=True,
        use_cache=True,
        redact_ips=False,
        redact_hostnames=False,
        require_mmdb=True,
    ),
    "private": Profile(
        name="private",
        description="Maximum privacy - no external lookups, full redaction",
        use_api=False,
        use_dns=False,
        use_cache=True,  # Can use cache but won't populate it
        redact_ips=True,
        redact_hostnames=True,
        require_mmdb=False,  # Can work with mock data
    ),
    "fast": Profile(
        name="fast",
        description="Prioritize speed with aggressive caching, no DNS",
        use_api=True,
        use_dns=False,  # Skip slow DNS lookups
        use_cache=True,
        redact_ips=False,
        redact_hostnames=False,
    ),
}


def get_profile(name: str) -> Profile:
    """
    Get profile by name.

    Args:
        name: Profile name (default, offline, private, fast)

    Returns:
        Profile configuration

    Raises:
        ValueError: If profile name is unknown
    """
    if name not in PROFILES:
        available = ", ".join(PROFILES.keys())
        raise ValueError(f"Unknown profile '{name}'. Available: {available}")

    return PROFILES[name]


def list_profiles() -> list[Profile]:
    """Get list of all available profiles."""
    return list(PROFILES.values())
