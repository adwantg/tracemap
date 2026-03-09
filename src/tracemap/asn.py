"""
ASN (Autonomous System Number) resolution.

Provides pluggable backends for IP to ASN lookup:
- TeamCymruResolver: DNS-based lookup (free, no database needed)
- PyASNResolver: Local database lookup (fast, requires pyasn package)
- CachingResolver: Wrapper that adds caching to any resolver

Author: gadwant
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class ASNInfo:
    """ASN information for an IP address."""

    asn: int
    org: Optional[str] = None
    prefix: Optional[str] = None
    country: Optional[str] = None


class ASNResolver(Protocol):
    """Protocol for ASN resolvers."""

    def lookup(self, ip: str) -> Optional[ASNInfo]:
        """Look up ASN information for an IP address."""
        ...


class TeamCymruResolver:
    """
    ASN resolver using Team Cymru's DNS-based service.

    This is a free service that works without any local database.
    Uses DNS queries to origin.asn.cymru.com.

    Example:
        resolver = TeamCymruResolver()
        info = resolver.lookup("8.8.8.8")
        # Returns ASNInfo(asn=15169, org="GOOGLE", ...)
    """

    def __init__(self, timeout: float = 2.0):
        """
        Initialize the resolver.

        Args:
            timeout: DNS query timeout in seconds
        """
        self.timeout = timeout
        socket.setdefaulttimeout(timeout)

    def _reverse_ip(self, ip: str) -> str:
        """Reverse an IP address for DNS query."""
        parts = ip.split(".")
        return ".".join(reversed(parts))

    def lookup(self, ip: str) -> Optional[ASNInfo]:
        """
        Look up ASN for an IP using Team Cymru DNS.

        The DNS query format is:
            <reversed-ip>.origin.asn.cymru.com

        Response format (TXT record):
            "ASN | IP Prefix | Country | Registry | Allocated Date"

        Example:
            8.8.8.8 -> 8.8.8.8.origin.asn.cymru.com
            Response: "15169 | 8.8.8.0/24 | US | arin | 1992-12-01"
        """
        try:
            # IPv4 only for now
            if ":" in ip:
                return None

            reversed_ip = self._reverse_ip(ip)
            query = f"{reversed_ip}.origin.asn.cymru.com"

            # Get TXT record
            import dns.resolver  # type: ignore[import-not-found, import-untyped]

            answers = dns.resolver.resolve(query, "TXT")

            for rdata in answers:
                txt = str(rdata).strip('"')
                parts = [p.strip() for p in txt.split("|")]

                if len(parts) >= 3:
                    asn = int(parts[0])
                    prefix = parts[1] if len(parts) > 1 else None
                    country = parts[2] if len(parts) > 2 else None

                    # Get ASN name
                    org = self._lookup_asn_name(asn)

                    return ASNInfo(
                        asn=asn,
                        prefix=prefix,
                        country=country,
                        org=org,
                    )

        except Exception:
            # DNS resolution failed
            pass

        return None

    @lru_cache(maxsize=1000)
    def _lookup_asn_name(self, asn: int) -> Optional[str]:
        """Look up the organization name for an ASN."""
        try:
            import dns.resolver  # type: ignore[import-not-found, import-untyped]

            query = f"AS{asn}.asn.cymru.com"
            answers = dns.resolver.resolve(query, "TXT")

            for rdata in answers:
                txt = str(rdata).strip('"')
                parts = [p.strip() for p in txt.split("|")]

                if len(parts) >= 5:
                    # Format: ASN | Country | Registry | Date | Name
                    return parts[4]

        except Exception:
            pass

        return None


class TeamCymruResolverSimple:
    """
    Simplified Team Cymru resolver using socket (no dnspython dependency).

    Uses whois-style queries over TCP to whois.cymru.com.
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def lookup(self, ip: str) -> Optional[ASNInfo]:
        """Look up ASN using Team Cymru whois service."""
        try:
            # IPv4 only
            if ":" in ip:
                return None

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(("whois.cymru.com", 43))

                # Send query with verbose flag for AS name
                query = f" -v {ip}\n"
                sock.sendall(query.encode("utf-8"))

                response = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk

            # Parse response
            # Format: AS | IP | BGP Prefix | CC | Registry | Allocated | AS Name
            lines = response.decode("utf-8").strip().split("\n")

            for line in lines:
                if line.startswith("AS"):
                    continue  # Skip header

                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 7:
                    try:
                        asn = int(parts[0].strip())
                        prefix = parts[2].strip() or None
                        country = parts[3].strip() or None
                        org = parts[6].strip() or None

                        return ASNInfo(
                            asn=asn,
                            prefix=prefix,
                            country=country,
                            org=org,
                        )
                    except ValueError:
                        continue

        except Exception:
            pass

        return None


class PyASNResolver:
    """
    ASN resolver using the pyasn library with local MRT/RIB database.

    This provides very fast lookups but requires downloading an ASN database.
    See: https://github.com/hadiasghari/pyasn
    """

    def __init__(self, database_path: Path, as_names_path: Optional[Path] = None):
        """
        Initialize with paths to pyasn database files.

        Args:
            database_path: Path to the pyasn .dat file
            as_names_path: Optional path to AS names file
        """
        import pyasn  # type: ignore

        self.asndb = pyasn.pyasn(str(database_path))

        self.as_names: dict[int, str] = {}
        if as_names_path and as_names_path.exists():
            self._load_as_names(as_names_path)

    def _load_as_names(self, path: Path) -> None:
        """Load AS names from a file."""
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    try:
                        asn = int(parts[0])
                        name = parts[1]
                        self.as_names[asn] = name
                    except ValueError:
                        continue

    def lookup(self, ip: str) -> Optional[ASNInfo]:
        """Look up ASN from local database."""
        try:
            asn, prefix = self.asndb.lookup(ip)
            if asn is None:
                return None

            org = self.as_names.get(asn)

            return ASNInfo(
                asn=asn,
                prefix=prefix,
                org=org,
            )

        except Exception:
            return None


class CachingResolver:
    """
    Wrapper that adds LRU caching to any ASN resolver.

    Example:
        base = TeamCymruResolverSimple()
        resolver = CachingResolver(base, maxsize=10000)
    """

    def __init__(self, resolver: ASNResolver, maxsize: int = 10000):
        """
        Initialize with a base resolver.

        Args:
            resolver: The underlying ASN resolver
            maxsize: Maximum cache size
        """
        self._resolver = resolver
        self._cache: dict[str, Optional[ASNInfo]] = {}
        self._maxsize = maxsize

    def lookup(self, ip: str) -> Optional[ASNInfo]:
        """Look up with caching."""
        if ip in self._cache:
            return self._cache[ip]

        # Evict oldest if at capacity (simple FIFO for now)
        if len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

        result = self._resolver.lookup(ip)
        self._cache[ip] = result
        return result

    def cache_stats(self) -> dict:
        """Return cache statistics."""
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
        }


def get_default_resolver() -> ASNResolver:
    """
    Get the default ASN resolver.

    Tries in order:
    1. PyASN if database exists
    2. Team Cymru simple (socket-based, no dependencies)
    """
    # Check for pyasn database in common locations
    db_paths = [
        Path.home() / ".tracemap" / "asn.dat",
        Path("/usr/local/share/pyasn/ipasn.dat"),
    ]

    for db_path in db_paths:
        if db_path.exists():
            try:
                return CachingResolver(PyASNResolver(db_path))
            except Exception:
                continue

    # Fall back to Team Cymru
    return CachingResolver(TeamCymruResolverSimple())
