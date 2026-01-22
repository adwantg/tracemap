from tracemap.trace import _parse_hop_line

def test_parse_hop_line_rtts():
    hop = _parse_hop_line(" 1  8.8.8.8  10.1 ms  11.2 ms  9.9 ms", probes=3)
    assert hop.hop == 1
    assert hop.ip == "8.8.8.8"
    assert len(hop.probes) == 3
    assert hop.probes[0].ok is True

def test_parse_hop_line_timeouts():
    hop = _parse_hop_line(" 3  * * *", probes=3)
    assert hop.hop == 3
    assert hop.ip is None
    assert hop.loss_pct == 100.0
