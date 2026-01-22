"""
Cache module for persistent storage of geo/ASN/DNS lookups.

Provides SQLite-based caching to:
- Avoid API rate limits
- Speed up repeated traces
- Enable offline operation
- Track data source and confidence

Author: gadwant
"""
from .sqlite import GeoCache, ASNCache, DNSCache

__all__ = ["GeoCache", "ASNCache", "DNSCache"]
