"""
Traceroute execution and parsing.

Supports:
- macOS and Linux traceroute variants
- IPv4 and IPv6
- UDP, TCP, and ICMP protocols

Author: gadwant
"""
from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Generator, List, Optional, Tuple

from rich.console import Console
from rich.live import Live

from .geo import GeoLocator
from .models import Hop, HopProbe, TraceMeta, TraceRun, is_private_ip
from .render import render_frame

console = Console()


class Protocol(str, Enum):
    """Traceroute protocol options."""

    UDP = "udp"
    TCP = "tcp"
    ICMP = "icmp"


@dataclass(frozen=True)
class TraceConfig:
    """Configuration for a traceroute run."""

    host: str
    max_hops: int = 30
    timeout_s: float = 2.0
    probes: int = 3
    protocol: Protocol = Protocol.UDP
    port: int = 33434  # Default UDP port for traceroute
    resolve_hostnames: bool = True  # Reverse DNS enabled by default
    source_interface: Optional[str] = None
    source_port: Optional[int] = None


def traceroute_binary() -> Optional[str]:
    """Find the traceroute binary on the system."""
    # Try common names
    for name in ["traceroute", "traceroute6"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def resolve_host(host: str) -> Tuple[str, Optional[str]]:
    """
    Resolve a hostname to an IP address.

    Returns:
        Tuple of (resolved_ip, address_family) or (host, None) if resolution fails
    """
    try:
        # Try IPv4 first
        info = socket.getaddrinfo(host, None, socket.AF_INET)
        if info:
            return info[0][4][0], "ipv4"
    except socket.gaierror:
        pass

    try:
        # Try IPv6
        info = socket.getaddrinfo(host, None, socket.AF_INET6)
        if info:
            return info[0][4][0], "ipv6"
    except socket.gaierror:
        pass

    return host, None


def _build_cmd(cfg: TraceConfig, binary: str) -> List[str]:
    """
    Build a traceroute command that works reasonably on macOS/Linux.

    Handles differences between BSD (macOS) and Linux traceroute.
    """
    system = platform.system().lower()
    is_macos = system == "darwin"

    cmd = [binary]

    # Numeric output (no DNS resolution during trace - faster)
    if not cfg.resolve_hostnames:
        cmd.append("-n")

    # Max hops
    cmd.extend(["-m", str(cfg.max_hops)])

    # Probes per hop
    cmd.extend(["-q", str(cfg.probes)])

    # Timeout per probe
    if is_macos:
        # macOS uses -w for wait time (seconds, can be float)
        cmd.extend(["-w", str(int(cfg.timeout_s))])
    else:
        # Linux uses -w for wait time (seconds)
        cmd.extend(["-w", str(int(cfg.timeout_s))])

    # Protocol selection
    if cfg.protocol == Protocol.ICMP:
        cmd.append("-I")  # ICMP Echo
    elif cfg.protocol == Protocol.TCP:
        cmd.append("-T")  # TCP SYN
        if not is_macos:
            cmd.extend(["-p", str(cfg.port)])

    # Source Interface
    if cfg.source_interface:
        cmd.extend(["-i", cfg.source_interface])
        
    # Source Port
    # Note: For UDP/TCP, -p is often destination port, -s is source address/port depending on version.
    # macOS traceroute: -s src_addr. No direct source port flag except varying start port?
    # Actually standard traceroute uses -p for DEST port (UDP/TCP).
    # If user wants to bind source port for Paris traceroute stabilization, that's complex.
    # But usually --source-port implies fixing the source port.
    # Linux traceroute: --sport=num
    # We will assume Linux-style --sport if provided, or ignore/warn if on mac without support?
    # For now, let's try to add if provided.
    if cfg.source_port:
        if is_macos:
             # macOS traceroute doesn't have an easy fixed source port flag for UDP
             pass 
        else:
             cmd.extend(["--sport", str(cfg.source_port)])

    # Target host
    cmd.append(cfg.host)

    return cmd


# Regex patterns for parsing traceroute output

# IPv4: 192.168.1.1
_IPV4_PATTERN = r"(?P<ip>\d{1,3}(?:\.\d{1,3}){3})"

# IPv6: 2001:db8::1 or ::1 or fe80::1%eth0
_IPV6_PATTERN = r"(?P<ip6>(?:[0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{1,4}|(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}|[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,4}[0-9a-fA-F]{1,4})"

# RTT value: 10.123 ms or 10.123ms
_RTT_PATTERN = r"(?P<rtt>\d+(?:\.\d+)?)\s*ms"

# Hop line: starts with hop number
_HOP_LINE_PATTERN = re.compile(r"^\s*(\d+)\s+(.*)$")

# Combined IP pattern (IPv4 or IPv6)
_IP_RE = re.compile(f"{_IPV4_PATTERN}|{_IPV6_PATTERN}")
_RTT_RE = re.compile(_RTT_PATTERN)

# Hostname with IP: hostname (ip) or just ip
# Use non-capturing groups to avoid conflicts
_HOSTNAME_PATTERN = re.compile(r"([\w\-\.]+)\s*\(([\d\.]+|[\da-fA-F:]+)\)")


def _extract_ip(text: str) -> Optional[str]:
    """Extract an IP address (v4 or v6) from text."""
    m = _IP_RE.search(text)
    if m:
        return m.group("ip") or m.group("ip6")
    return None


def _extract_hostname_and_ip(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract hostname and IP from various formats:
    - hostname (ip)
    - ip
    - (ip)
    """
    # Try hostname (ip) format first
    m = re.search(r"([\w\-\.]+)\s*\(([\d\.]+|[\da-fA-F:]+)\)", text)
    if m:
        return m.group(1), m.group(2)

    # Just IP
    ip = _extract_ip(text)
    return None, ip


def _parse_hop_line(line: str, probes: int) -> Optional[Hop]:
    """
    Parse a single traceroute hop line.

    Handles various formats:
    - BSD/macOS: ' 1  192.168.1.1  1.123 ms  0.987 ms  1.050 ms'
    - Linux: ' 1  192.168.1.1 (192.168.1.1)  1.123 ms  0.987 ms  1.050 ms'
    - Timeout: ' 3  * * *'
    - Mixed: ' 4  8.8.8.8  20.1 ms  *  19.9 ms'
    - With hostname: ' 5  router.example.com (10.0.0.1)  5.2 ms  5.1 ms  5.0 ms'
    """
    m = _HOP_LINE_PATTERN.match(line)
    if not m:
        return None

    hop_no = int(m.group(1))
    rest = m.group(2)

    # Extract hostname and IP
    hostname, ip = _extract_hostname_and_ip(rest)

    # Find all RTT values
    rtts = [float(x) for x in _RTT_RE.findall(rest)]

    # Count timeouts (asterisks)
    star_count = rest.count("*")

    # Build probes list
    hop_probes: List[HopProbe] = []

    # Add successful probes
    for rtt in rtts[:probes]:
        hop_probes.append(HopProbe(rtt_ms=rtt, ok=True))

    # Add timeout probes
    for _ in range(min(star_count, probes - len(hop_probes))):
        hop_probes.append(HopProbe(rtt_ms=None, ok=False))

    # Pad with timeouts if needed
    while len(hop_probes) < probes:
        hop_probes.append(HopProbe(rtt_ms=None, ok=False))

    # Determine if fully timed out
    is_timeout = ip is None and all(not p.ok for p in hop_probes)

    # Check if private IP
    is_private = is_private_ip(ip) if ip else False

    return Hop(
        hop=hop_no,
        ip=ip,
        hostname=hostname,
        probes=hop_probes,
        is_private=is_private,
        is_timeout=is_timeout,
    )


def _parse_traceroute_output(
    lines: Generator[str, None, None], probes: int
) -> Generator[Hop, None, None]:
    """
    Parse traceroute output lines and yield Hop objects.

    Skips header lines and handles both IPv4 and IPv6 output.
    """
    for line in lines:
        line = line.rstrip("\n\r")

        # Skip header lines
        lower = line.lower()
        if lower.startswith("traceroute") or lower.startswith("tracert"):
            continue
        if not line.strip():
            continue

        hop = _parse_hop_line(line, probes)
        if hop:
            yield hop


def run_traceroute(
    cfg: TraceConfig,
    geoloc: GeoLocator,
    live_render: bool = True,
    render_map: bool = False,
) -> TraceRun:
    """
    Execute traceroute and return parsed results.

    Args:
        cfg: Trace configuration
        geoloc: GeoIP locator for resolving IP locations
        live_render: Whether to render live updates in terminal
        render_map: Whether to show ASCII map (deprecated, shows table by default)

    Returns:
        TraceRun with all hops and metadata
    """
    binary = traceroute_binary()
    if not binary:
        console.print("[red]traceroute binary not found.[/red]")
        raise RuntimeError("traceroute not found")

    # Resolve host to get IP
    resolved_ip, addr_family = resolve_host(cfg.host)

    cmd = _build_cmd(cfg, binary)

    meta = TraceMeta(
        host=cfg.host,
        resolved_ip=resolved_ip if resolved_ip != cfg.host else None,
        max_hops=cfg.max_hops,
        probes=cfg.probes,
        timeout_s=cfg.timeout_s,
        protocol=cfg.protocol.value,
        started_at=datetime.now(timezone.utc),
    )
    trace = TraceRun(meta=meta, hops=[])

    console.print()
    console.print(f"[bold cyan]Tracing to {cfg.host}...[/bold cyan]")
    if resolved_ip:
        console.print(f"[dim]Resolved to {resolved_ip}[/dim]")
    console.print()

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    assert proc.stdout is not None

    def line_generator() -> Generator[str, None, None]:
        assert proc.stdout is not None
        for line in proc.stdout:
            yield line

    if live_render:
        # Render frame based on mode (map or table)
        if render_map:
            # Deprecated: ASCII map mode
            with Live(render_frame(trace), refresh_per_second=8, console=console) as live:
                for hop in _parse_traceroute_output(line_generator(), cfg.probes):
                    # Resolve geo for responding hops
                    if hop.ip and not hop.is_private:
                        hop.geo = geoloc.locate(hop.ip)

                    trace.hops.append(hop)
                    live.update(render_frame(trace))
        else:
            # Default: Clean table mode
            from .render import _hop_table
            with Live(_hop_table(trace), refresh_per_second=2, console=console) as live:
                for hop in _parse_traceroute_output(line_generator(), cfg.probes):
                    # Resolve geo for responding hops
                    if hop.ip and not hop.is_private:
                        hop.geo = geoloc.locate(hop.ip)

                    trace.hops.append(hop)
                    live.update(_hop_table(trace))
    else:
        for hop in _parse_traceroute_output(line_generator(), cfg.probes):
            if hop.ip and not hop.is_private:
                hop.geo = geoloc.locate(hop.ip)
            trace.hops.append(hop)

    proc.wait()

    # Update completion time
    meta.completed_at = datetime.now(timezone.utc)

    return trace


def parse_traceroute_file(filepath: str, probes: int = 3) -> List[Hop]:
    """
    Parse a saved traceroute output file.

    Args:
        filepath: Path to the traceroute output file
        probes: Expected number of probes per hop

    Returns:
        List of parsed Hop objects
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = (line for line in f)
        return list(_parse_traceroute_output(lines, probes))
