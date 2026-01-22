"""
Geographic confidence scoring and plausibility checks.

Provides confidence indicators for geo-location data based on:
- Data source (API > MMDB > mock)
- IP type (public > private)
- Source agreement (multiple APIs agree)
- Plausibility (RTT vs distance, ocean crossings)

Author: gadwant
"""
from typing import Optional
import math

from ..models import Hop, HopGeo


class ConfidenceScorer:
    """Score geo-location confidence."""
    
    # Speed of light in fiber: ~200,000 km/s = 200 km/ms
    FIBER_SPEED_KM_PER_MS = 200.0
    
    def score_hop(self, hop: Hop, prev_hop: Optional[Hop] = None, metadata: Optional[dict] = None) -> str:
        """
        Compute confidence level for hop geo data.
        
        Args:
            hop: Hop to score
            prev_hop: Previous hop for plausibility checks
            metadata: Optional metadata (api_source, etc.)
            
        Returns:
            Confidence level: 'high', 'medium', 'low'
        """
        if not hop.geo:
            return "low"
        
        score = 0
        metadata = metadata or {}
        
        # Source quality (0-30 points)
        source = metadata.get("source", "unknown")
        if source in ("ip-api", "ipapi"):
            score += 30  # API data is most reliable
        elif source == "mmdb":
            score += 25  # Local DB is good
        elif source == "mock":
            score += 0   # Mock data is unreliable
        else:
            score += 15  # Unknown source
        
        # IP type (0-25 points)
        if not hop.is_private:
            score += 25  # Public IP can be geo-located
        else:
            score += 5   # Private IP has approximate location
        
        # ASN present (0-20 points)
        if hop.geo.asn:
            score += 20  # ASN adds credibility
        
        # Hostname correlation (0-15 points)
        if hop.hostname and hop.geo.city:
            # Simple heuristic: check if city name in hostname
            if hop.geo.city.lower() in hop.hostname.lower():
                score += 15
            elif hop.geo.country_code and hop.geo.country_code.lower() in hop.hostname.lower():
                score += 10
        
        # Plausibility check with previous hop (0-10 points)
        if prev_hop and prev_hop.geo and hop.rtt_avg_ms and prev_hop.rtt_avg_ms:
            rtt_delta = abs(hop.rtt_avg_ms - prev_hop.rtt_avg_ms)
            distance_km = self._haversine_distance(
                prev_hop.geo.lat, prev_hop.geo.lon,
                hop.geo.lat, hop.geo.lon
            )
            
            # Check speed-of-light bound
            min_rtt = distance_km / self.FIBER_SPEED_KM_PER_MS
            if rtt_delta >= min_rtt:
                score += 10  # Plausible timing
            else:
                score -= 10  # Violates physics - suspicious
        
        # Determine confidence level
        if score >= 70:
            return "high"
        elif score >= 40:
            return "medium"
        else:
            return "low"
    
    def check_ocean_crossing(self, hop1: Hop, hop2: Hop) -> bool:
        """
        Detect if route crosses an ocean between hops.
        
        Simple heuristic: large distance + different continents.
        """
        if not (hop1.geo and hop2.geo):
            return False
        
        distance_km = self._haversine_distance(
            hop1.geo.lat, hop1.geo.lon,
            hop2.geo.lat, hop2.geo.lon
        )
        
        # Ocean crossings typically >3000km
        if distance_km > 3000:
            # Different continents (simplified check)
            if hop1.geo.country_code != hop2.geo.country_code:
                return True
        
        return False
    
    def check_speed_of_light_bound(self, hop1: Hop, hop2: Hop) -> tuple[bool, Optional[str]]:
        """
        Check if RTT delta violates speed-of-light bound.
        
        Returns:
            (is_plausible, error_message)
        """
        if not (hop1.geo and hop2.geo and hop1.rtt_avg_ms and hop2.rtt_avg_ms):
            return True, None
        
        rtt_delta = abs(hop2.rtt_avg_ms - hop1.rtt_avg_ms)
        distance_km = self._haversine_distance(
            hop1.geo.lat, hop1.geo.lon,
            hop2.geo.lat, hop2.geo.lon
        )
        
        # Minimum RTT for this distance (assuming fiber optic)
        min_rtt = distance_km / self.FIBER_SPEED_KM_PER_MS
        
        if rtt_delta < min_rtt:
            error = (
                f"RTT delta ({rtt_delta:.1f}ms) < minimum for distance ({distance_km:.0f}km = {min_rtt:.1f}ms). "
                "Geo data may be incorrect (anycast, VPN, or incorrect location)."
            )
            return False, error
        
        return True, None
    
    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance in kilometers."""
        R = 6371.0  # Earth radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
