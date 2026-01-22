"""
Watch mode for continuous traceroute monitoring (MTR-style).

Continuously traces a host and tracks:
- Route changes (new hops, IP changes)
- RTT trends and spikes
- Packet loss patterns
- ASN changes (BGP shifts)

Author: gadwant
"""
from .monitor import TraceMonitor
from .alerts import AnomalyDetector

__all__ = ["TraceMonitor", "AnomalyDetector"]
