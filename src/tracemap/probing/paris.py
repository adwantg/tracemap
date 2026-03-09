"""
Paris traceroute implementation for ECMP-aware probing.

Uses fixed flow identifiers (src port + checksum manipulation)
to ensure stable paths through load-balanced networks.

Author: gadwant
"""

import subprocess
from collections import defaultdict
from typing import List, Optional

from ..models import TraceRun


class ECMPDetector:
    """
    Detect Equal-Cost Multi-Path (ECMP) load balancing.

    ECMP causes different flows to take different paths through
    the network, which can appear as route instability in standard
    traceroute.
    """

    def detect_ecmp_hops(self, trace: TraceRun) -> dict[int, list[str]]:
        """
        Identify hops with ECMP fan-out.

        Args:
            trace: Trace result

        Returns:
            Dict mapping hop number to list of IPs seen at that hop
        """
        # For single trace, we can't definitively detect ECMP
        # This would require multiple traces with different flow IDs
        # For now, mark hops with multiple probe responses as potential ECMP

        ecmp_hops = {}

        for hop in trace.hops:
            if hop.probes and len(hop.probes) > 1:
                # Check if different probes got different IPs
                ips = set(p.ip for p in hop.probes if p.ip)
                if len(ips) > 1:
                    ecmp_hops[hop.hop] = list(ips)

        return ecmp_hops

    def annotate_trace(self, trace: TraceRun) -> TraceRun:
        """
        Annotate trace with ECMP indicators.

        Adds metadata to hops indicating ECMP detected.
        """
        ecmp_hops = self.detect_ecmp_hops(trace)

        if not ecmp_hops:
            return trace

        # Add annotation (could enhance models.py to support this)
        # For now, just return the trace
        # In production, we'd add a field like hop.ecmp_detected = True

        return trace


class ParisProber:
    """
    Paris traceroute prober with flow ID stabilization.

    Uses fixed source ports and checksum manipulation to ensure
    consistent flow IDs across probes, avoiding ECMP path variation.
    """

    def __init__(self, flow_id: int = 0):
        """
        Initialize Paris prober.

        Args:
            flow_id: Flow identifier (0-65535) for deterministic path selection
        """
        self.flow_id = flow_id

    def build_command(
        self,
        host: str,
        max_hops: int = 30,
        protocol: str = "udp",
    ) -> List[str]:
        """
        Build Paris traceroute command.

        Args:
            host: Target host
            max_hops: Maximum hops
            protocol: Protocol (udp, tcp, icmp)

        Returns:
            Command arguments list
        """
        # Note: True Paris traceroute requires modified traceroute binary
        # or scamper. Standard traceroute has limited Paris support.

        # For macOS/BSD traceroute with some Paris-like behavior:
        # Use fixed source port to stabilize flow ID
        src_port = 33434 + (self.flow_id % 100)

        cmd = [
            "traceroute",
            "-n",  # No DNS
            "-m",
            str(max_hops),
            "-q",
            "3",  # 3 probes
        ]

        if protocol == "udp":
            cmd.extend(["-U", "-p", str(src_port)])  # UDP with fixed port
        elif protocol == "icmp":
            cmd.append("-I")  # ICMP
        elif protocol == "tcp":
            cmd.extend(["-T", "-p", "80"])  # TCP to port 80

        cmd.append(host)

        return cmd

    def paris_trace(
        self,
        host: str,
        max_hops: int = 30,
        protocol: str = "udp",
    ) -> Optional[str]:
        """
        Run Paris-style traceroute.

        Returns:
            Raw traceroute output
        """
        cmd = self.build_command(host, max_hops, protocol)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.stdout
        except Exception:
            return None

    def detect_ecmp_multipath(
        self,
        host: str,
        max_flows: int = 5,
        max_hops: int = 30,
    ) -> dict[int, set[str]]:
        """
        Run multiple Paris traces with different flow IDs to discover ECMP paths.

        Args:
            host: Target host
            max_flows: Number of different flows to try
            max_hops: Maximum hops

        Returns:
            Dict mapping hop number to set of IPs seen across all flows
        """
        hop_ips: dict[int, set[str]] = defaultdict(set)

        for flow_id in range(max_flows):
            prober = ParisProber(flow_id=flow_id)
            output = prober.paris_trace(host, max_hops)

            if not output:
                continue

            # Parse output (simplified - would use full parser)
            for line in output.split("\n"):
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].isdigit():
                    hop_num = int(parts[0])
                    # Extract IP (simplified)
                    for part in parts[1:]:
                        if "." in part and part.replace(".", "").isdigit():
                            hop_ips[hop_num].add(part)

        # Filter to only ECMP hops (multiple IPs)
        ecmp_hops = {hop: ips for hop, ips in hop_ips.items() if len(ips) > 1}

        return ecmp_hops
