"""
Anomaly detection for trace monitoring.

Detects:
- Route changes (new hop, IP change, ASN change)
- RTT spikes (>40% from baseline)
- Loss threshold exceeded
- Hop count changes

Author: gadwant
"""
from typing import Optional

from ..models import TraceRun


class AnomalyDetector:
    """Detect anomalies between consecutive traces."""
    
    def __init__(self, thresholds: Optional[dict] = None):
        """
        Initialize detector with thresholds.
        
        Args:
            thresholds: Dict with 'rtt_spike' (default 0.4) and 'loss' (default 0.05)
        """
        self.thresholds = thresholds or {}
        self.rtt_spike_threshold = self.thresholds.get("rtt_spike", 0.4)  # 40%
        self.loss_threshold = self.thresholds.get("loss", 0.05)  # 5%
    
    def detect(
        self,
        prev_trace: TraceRun,
        curr_trace: TraceRun,
        hop_stats: dict
    ) -> list[str]:
        """
        Detect anomalies between traces.
        
        Returns:
            List of anomaly descriptions
        """
        anomalies = []
        
        # Check hop count change
        if len(curr_trace.hops) != len(prev_trace.hops):
            anomalies.append(
                f"Hop count changed: {len(prev_trace.hops)} → {len(curr_trace.hops)}"
            )
        
        # Check each hop
        max_hops = max(len(prev_trace.hops), len(curr_trace.hops))
        
        for i in range(max_hops):
            hop_num = i + 1
            prev_hop = prev_trace.hops[i] if i < len(prev_trace.hops) else None
            curr_hop = curr_trace.hops[i] if i < len(curr_trace.hops) else None
            
            if not prev_hop or not curr_hop:
                continue
            
            # IP change
            if prev_hop.ip != curr_hop.ip and prev_hop.ip and curr_hop.ip:
                anomalies.append(
                    f"Hop {hop_num}: IP changed {prev_hop.ip} → {curr_hop.ip}"
                )
            
            # ASN change
            if (prev_hop.geo and curr_hop.geo and
                prev_hop.geo.asn and curr_hop.geo.asn and
                prev_hop.geo.asn != curr_hop.geo.asn):
                anomalies.append(
                    f"Hop {hop_num}: ASN changed AS{prev_hop.geo.asn} → AS{curr_hop.geo.asn}"
                )
            
            # RTT spike
            if (prev_hop.rtt_avg_ms and curr_hop.rtt_avg_ms and
                hop_num in hop_stats):
                stats = hop_stats[hop_num]
                if stats.avg_rtt:
                    spike = (curr_hop.rtt_avg_ms - stats.avg_rtt) / stats.avg_rtt
                    if spike > self.rtt_spike_threshold:
                        anomalies.append(
                            f"Hop {hop_num}: RTT spike +{spike*100:.0f}% "
                            f"({stats.avg_rtt:.1f}ms → {curr_hop.rtt_avg_ms:.1f}ms)"
                        )
            
            # Loss threshold
            if hop_num in hop_stats:
                stats = hop_stats[hop_num]
                if stats.loss_pct > self.loss_threshold * 100:
                    anomalies.append(
                        f"Hop {hop_num}: High loss {stats.loss_pct:.1f}%"
                    )
        
        return anomalies
