"""
Data models for traceroute visualization.

Author: gadwant
"""
from __future__ import annotations

import platform
import statistics
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


class HopGeo(BaseModel):
    """Geographic location data for a hop."""

    lat: float
    lon: float
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    # ASN information
    asn: Optional[int] = None
    asn_org: Optional[str] = None


class HopProbe(BaseModel):
    """Individual probe result for a hop."""

    rtt_ms: Optional[float] = None
    ok: bool = True


class Hop(BaseModel):
    """A single hop in a traceroute."""

    hop: int
    ip: Optional[str] = None
    hostname: Optional[str] = None  # Reverse DNS
    probes: List[HopProbe] = Field(default_factory=list)
    geo: Optional[HopGeo] = None
    is_private: bool = False  # RFC1918 private IP
    is_timeout: bool = False  # All probes timed out

    @computed_field  # type: ignore[misc]
    @property
    def loss_pct(self) -> float:
        """Packet loss percentage."""
        if not self.probes:
            return 100.0
        lost = sum(1 for p in self.probes if not p.ok)
        return 100.0 * lost / len(self.probes)

    @computed_field  # type: ignore[misc]
    @property
    def rtt_avg_ms(self) -> Optional[float]:
        """Average RTT in milliseconds."""
        vals = [p.rtt_ms for p in self.probes if p.ok and p.rtt_ms is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    @computed_field  # type: ignore[misc]
    @property
    def rtt_min_ms(self) -> Optional[float]:
        """Minimum RTT in milliseconds."""
        vals = [p.rtt_ms for p in self.probes if p.ok and p.rtt_ms is not None]
        if not vals:
            return None
        return min(vals)

    @computed_field  # type: ignore[misc]
    @property
    def rtt_max_ms(self) -> Optional[float]:
        """Maximum RTT in milliseconds."""
        vals = [p.rtt_ms for p in self.probes if p.ok and p.rtt_ms is not None]
        if not vals:
            return None
        return max(vals)

    @computed_field  # type: ignore[misc]
    @property
    def jitter_ms(self) -> Optional[float]:
        """Jitter (standard deviation of RTT) in milliseconds."""
        vals = [p.rtt_ms for p in self.probes if p.ok and p.rtt_ms is not None]
        if len(vals) < 2:
            return None
        return statistics.stdev(vals)

    @property
    def display_ip(self) -> str:
        """IP for display, or '*' if unknown."""
        return self.ip or "*"

    @property
    def display_geo(self) -> str:
        """Geographic location for display."""
        if not self.geo:
            return ""
        parts = []
        if self.geo.city:
            parts.append(self.geo.city)
        if self.geo.country:
            parts.append(self.geo.country)
        if parts:
            return ", ".join(parts)
        return f"{self.geo.lat:.2f}, {self.geo.lon:.2f}"

    @property
    def display_asn(self) -> str:
        """ASN for display."""
        if not self.geo or not self.geo.asn:
            return ""
        if self.geo.asn_org:
            return f"AS{self.geo.asn} ({self.geo.asn_org})"
        return f"AS{self.geo.asn}"


class TraceMeta(BaseModel):
    """Metadata about a trace run."""

    tool: str = "tracemap"
    version: str = "0.1.0"
    host: str
    resolved_ip: Optional[str] = None
    max_hops: int
    probes: int
    timeout_s: float
    protocol: str = "udp"  # udp, tcp, icmp
    # Timestamps and platform
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    platform_system: str = Field(default_factory=platform.system)
    platform_release: str = Field(default_factory=platform.release)


class TraceRun(BaseModel):
    """Complete trace run with metadata and hops."""

    meta: TraceMeta
    hops: List[Hop] = Field(default_factory=list)

    @computed_field  # type: ignore[misc]
    @property
    def total_hops(self) -> int:
        """Total number of hops."""
        return len(self.hops)

    @computed_field  # type: ignore[misc]
    @property
    def responded_hops(self) -> int:
        """Number of hops that responded (not timeout)."""
        return sum(1 for h in self.hops if not h.is_timeout and h.ip)

    @computed_field  # type: ignore[misc]
    @property
    def timeout_hops(self) -> int:
        """Number of hops that timed out."""
        return sum(1 for h in self.hops if h.is_timeout)

    @computed_field  # type: ignore[misc]
    @property
    def avg_loss_pct(self) -> float:
        """Average packet loss across all hops."""
        if not self.hops:
            return 0.0
        return sum(h.loss_pct for h in self.hops) / len(self.hops)

    @property
    def geo_hops(self) -> List[Hop]:
        """Hops that have geo information."""
        return [h for h in self.hops if h.geo]

    def get_detour_alerts(self, distance_threshold_km: float = 5000) -> List[str]:
        """
        Detect unusual route detours (e.g., continent jumps).

        Args:
            distance_threshold_km: Distance threshold to consider a detour

        Returns:
            List of alert messages for detected detours
        """
        alerts = []
        geo_hops = self.geo_hops

        for i in range(1, len(geo_hops)):
            prev = geo_hops[i - 1]
            curr = geo_hops[i]

            if prev.geo and curr.geo:
                dist = _haversine_km(
                    prev.geo.lat, prev.geo.lon, curr.geo.lat, curr.geo.lon
                )
                if dist > distance_threshold_km:
                    alerts.append(
                        f"Detour detected: hop {prev.hop}→{curr.hop} spans {dist:.0f}km"
                    )

        return alerts


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    import math

    R = 6371  # Earth's radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def is_private_ip(ip: str) -> bool:
    """
    Check if IP is private/non-routable.
    
    Includes:
    - RFC1918 private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Loopback (127.0.0.0/8)
    - Link-local (169.254.0.0/16)
    - **CGNAT range (100.64.0.0/10)** - Carrier-Grade NAT
    
    CGNAT addresses are used by ISPs for large-scale NAT and are not
    publicly routable. GeoIP APIs do not have data for these addresses.
    """
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
        
        # Standard private/loopback/link-local check
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return True
        
        # CGNAT range check (100.64.0.0/10)
        # Carrier-Grade NAT - RFC 6598
        cgnat = ipaddress.ip_network('100.64.0.0/10')
        if addr in cgnat:
            return True
            
        return False
    except ValueError:
        return False
