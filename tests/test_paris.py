import pytest
from unittest.mock import MagicMock, patch
from tracemap.probing.paris import ParisProber, ECMPDetector
from tracemap.models import TraceRun, Hop, HopProbe

class TestParisProber:
    def test_build_command_default(self):
        prober = ParisProber(flow_id=12345)
        cmd = prober.build_command("example.com")
        
        assert cmd[0] == "traceroute"
        assert "-n" in cmd
        assert "-U" in cmd
        # Verify fixed port logic: 33434 + (12345 % 100) = 33434 + 45 = 33479
        assert "33479" in cmd
        assert cmd[-1] == "example.com"

    def test_build_command_icmp(self):
        prober = ParisProber()
        cmd = prober.build_command("example.com", protocol="icmp")
        assert "-I" in cmd
        assert "-U" not in cmd

    def test_build_command_tcp(self):
        prober = ParisProber()
        cmd = prober.build_command("example.com", protocol="tcp")
        assert "-T" in cmd
        assert "-p" in cmd
        assert "80" in cmd

    @patch("subprocess.run")
    def test_paris_trace_execution(self, mock_run):
        mock_run.return_value = MagicMock(stdout="1 1.1.1.1 10ms", returncode=0)
        prober = ParisProber()
        output = prober.paris_trace("example.com")
        
        mock_run.assert_called_once()
        assert output == "1 1.1.1.1 10ms"

    @patch("tracemap.probing.paris.ParisProber.paris_trace")
    def test_detect_ecmp_multipath(self, mock_trace):
        # Mock responses for different flow IDs
        # Flow 0: Hop 1 -> 1.1.1.1
        # Flow 1: Hop 1 -> 1.1.1.2 (ECMP!)
        
        def side_effect(host, max_hops):
            if mock_trace.call_count == 1:
                return "1 1.1.1.1"
            else:
                return "1 1.1.1.2"
        
        mock_trace.side_effect = side_effect
        
        prober = ParisProber()
        ecmp_map = prober.detect_ecmp_multipath("example.com", max_flows=2)
        
        assert 1 in ecmp_map
        assert len(ecmp_map[1]) == 2
        assert "1.1.1.1" in ecmp_map[1]
        assert "1.1.1.2" in ecmp_map[1]


class TestECMPDetector:
    def test_detect_ecmp_hops_single_trace(self):
        # Create a trace where hop 2 has responses from different IPs
        h2 = Hop(
            hop=2, 
            probes=[
                HopProbe(ip="2.2.2.1", rtt_ms=10, ok=True),
                HopProbe(ip="2.2.2.2", rtt_ms=11, ok=True),  # Different IP
                HopProbe(ip="2.2.2.1", rtt_ms=12, ok=True)
            ]
        )
        h3 = Hop(
            hop=3,
            probes=[
                HopProbe(ip="3.3.3.3", rtt_ms=20, ok=True),
                HopProbe(ip="3.3.3.3", rtt_ms=21, ok=True)
            ]
        )
        
        # Determine meta fields required by TraceRun validator
        # Ideally we'd validte this properly, but for unit test mocking minimal fields
        trace = TraceRun(
            meta={
                "tool": "test", 
                "version": "1.0", 
                "host": "test.com", 
                "max_hops": 30,
                "probes": 3,
                "timeout_s": 2.0,
                "started_at": "2023-01-01T00:00:00"
            },
            hops=[h2, h3]
        )
        
        detector = ECMPDetector()
        ecmp_hops = detector.detect_ecmp_hops(trace)
        
        assert 2 in ecmp_hops
        assert len(ecmp_hops[2]) == 2
        assert 3 not in ecmp_hops
