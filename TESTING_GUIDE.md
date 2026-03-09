# Tracemap v0.3.0 - Complete Feature Testing Guide

## 🎯 Goal
Test every feature locally to ensure production readiness.

**Time Required**: ~30 minutes  
**Prerequisites**: Package installed with `pip install -e .`

---

## ✅ Pre-Flight Check

### 1. Verify Installation
```bash
cd ~/Documents/OpenSource/PythonProjects/traceroute-map-tui

# Install in editable mode
pip install -e .

# Verify command exists
which tracemap

# Check version and help
tracemap --help
```

**Expected**: Help text showing all commands (trace, watch, cache, export, diff, stats, tui, replay, doctor)

---

## 🧪 Feature Testing

### Test 1: Basic Trace Command ⭐⭐⭐

**Purpose**: Verify core functionality

```bash
# Run basic trace
tracemap trace google.com

# What to verify:
# ✓ Clean table output (no endless * * *)
# ✓ Hop numbers, IPs, RTT values
# ✓ Auto-generated files: .tracemap/trace.json + trace.html
```

**Expected Output**:
```
╭────┬──────────────┬──────────────┬─────────┬──────┬──────────┬──────────╮
│ #  │ IP           │ Hostname     │ Avg RTT │ Loss │ ASN      │ Location │
├────┼──────────────┼──────────────┼─────────┼──────┼──────────┼──────────┤
│  1 │ 192.168.1.1  │ gateway      │   2ms   │  0%  │          │          │
│  2 │ 10.x.x.x     │ ...          │  15ms   │  0%  │ AS7922   │ City, US │
...
✓ Saved: .tracemap/trace.json
✓ Saved: .tracemap/trace.html
```

**Verification**:
```bash
# Check generated files
ls -lh .tracemap/

# Should see:
# - trace.json (structured data)
# - trace.html (interactive map)
```

---

### Test 2: Cache System ⭐⭐⭐

**Purpose**: Verify persistent SQLite caching

```bash
# First run (cold cache)
time tracemap trace google.com
# Note the execution time (e.g., 8-12 seconds)

# Second run (warm cache)
time tracemap trace google.com
# Should be MUCH faster (2-3 seconds) ⚡

# View cache stats
tracemap cache stats
```

**Expected Output**:
```
Cache Database: ~/.tracemap/cache.sqlite

Total entries: 12
Valid entries: 12
Expired entries: 0

Session Statistics:
  Hits: 10
  Misses: 2
  Hit rate: 83.3%
```

**Verification**:
```bash
# Check cache file exists
ls -lh ~/.tracemap/cache.sqlite

# Should be > 0 bytes

# Clear cache (testing)
tracemap cache clear

# Verify cleared
tracemap cache stats
# Should show 0 entries
```

---

### Test 3: Privacy Profiles ⭐⭐⭐

**Purpose**: Test offline and privacy modes

```bash
# Test 1: Private profile (no external calls)
tracemap trace --profile private google.com

# What to verify:
# ✓ No API calls made
# ✓ IPs redacted in output
# ✓ Faster execution (no network lookups)

# Test 2: Fast profile (skip DNS)
tracemap trace --profile fast google.com

# What to verify:
# ✓ No hostname column populated
# ✓ Faster execution

# Test 3: Default profile
tracemap trace --profile default google.com

# What to verify:
# ✓ Full API + DNS lookups
# ✓ Complete data
```

**Expected (Private)**:
```
│  1 │ [redacted:a3f...]  │           │   2ms   │  0%  │          │          │
│  2 │ [redacted:b8d...]  │           │  15ms   │  0%  │          │          │
```

---

### Test 4: Watch Mode (MTR Parity) ⭐⭐⭐

**Purpose**: Continuous monitoring with anomaly detection

```bash
# Start watch mode (Ctrl+C to stop after ~1 minute)
tracemap watch google.com --interval 10

# What to verify:
# ✓ Table updates every 10 seconds
# ✓ Rolling statistics (Avg RTT, Loss %)
# ✓ Sample count increases
# ✓ Alerts appear if route changes

# Check log file
cat ~/.tracemap/watch_google.com.jsonl | head -5
```

**Expected Output**:
```
Monitoring: google.com (interval: 10s)

╭────┬──────────────┬─────────────┬──────┬────────┬─────────╮
│ #  │ IP           │ Avg RTT     │ Loss │ Samples│ Alerts  │
├────┼──────────────┼─────────────┼──────┼────────┼─────────┤
│  1 │ 192.168.1.1  │   2.1ms     │  0%  │   5    │         │
│  2 │ 10.x.x.x     │  15.3ms     │  0%  │   5    │         │
...

[Updates every 10s]
```

---

### Test 5: ECMP Detection (Paris Traceroute) ⭐⭐

**Purpose**: Detect load-balanced paths

```bash
# Discover multiple paths
tracemap trace --discover-paths google.com

# What to verify:
# ✓ Takes 30-60 seconds (multiple flows)
# ✓ Shows ECMP hops if detected
# ✓ Lists different IPs at same hop

# Paris mode
tracemap trace --paris google.com

# What to verify:
# ✓ More stable path (fewer variations)
```

**Expected Output (if ECMP detected)**:
```
Discovering ECMP paths...
This may take 30-60 seconds...

⚠️  ECMP detected at 2 hops:
  Hop 4: 2 paths
    - 68.85.155.117
    - 68.85.155.161
  Hop 7: 3 paths
    - 162.151.86.57
    - 162.151.86.89
    - 162.151.87.13
```

---

### Test 6: Export Formats ⭐⭐⭐

**Purpose**: Test all export formats

```bash
# Ensure you have a trace file
tracemap trace google.com --out test_trace.json

# Test 1: HTML Export
tracemap export test_trace.json --format html --out test.html

# Verify
ls -lh test.html
open test.html  # macOS - should open in browser

# Test 2: SVG Export
tracemap export test_trace.json --format svg --out test.svg

# Verify
ls -lh test.svg
open test.svg  # Should show static map

# Test 3: Markdown Export ⭐ NEW
tracemap export test_trace.json --format markdown --out test.md

# Verify
cat test.md
```

**Expected (Markdown)**:
```
# Traceroute Report: google.com

**Date**: 2026-01-22 11:00:00 UTC
**Duration**: 8.5s
**Hops**: 12 (10 responded)
**Protocol**: UDP

## Route Summary

| Hop | IP | Hostname | RTT | Loss | ASN | Location |
|-----|----|----|-----|------|-----|----------|
| 1 | 192.168.1.1 | gateway | 2.1ms | 0% | | |
...

## Statistics
**RTT**: min 2.1ms, avg 15.3ms, max 45.2ms
...
```

---

### Test 7: TUI Mode ⭐⭐

**Purpose**: Interactive terminal UI

```bash
# Launch TUI with existing trace
tracemap tui test_trace.json

# What to test:
# ✓ Press ↑/↓ or j/k to navigate hops
# ✓ Press Enter to view hop details
# ✓ Press 'e' to export to HTML
# ✓ Press 'r' to refresh
# ✓ Press 'q' to quit

# Launch empty TUI
tracemap tui
```

**Expected**: Split-screen interface with map, hop table, and metadata panels.

---

### Test 8: Replay & Diff ⭐⭐

**Purpose**: Replay saved traces and compare

```bash
# Replay a trace (without re-running)
tracemap replay test_trace.json

# Should show same output as original trace

# Create second trace for comparison
tracemap trace google.com --out trace_morning.json

# Wait a few hours or use different target
tracemap trace google.com --out trace_evening.json

# Compare traces
tracemap diff trace_morning.json trace_evening.json
```

**Expected (Diff)**:
```
╭───┬─────────────────┬─────────────────┬───────╮
│ # │ Trace A IP      │ Trace B IP      │ Match │
├───┼─────────────────┼─────────────────┼───────┤
│ 1 │ 192.168.1.1     │ 192.168.1.1     │   ✓   │
│ 2 │ 10.0.0.1        │ 10.0.0.1        │   ✓   │
│ 3 │ 203.0.113.1     │ 198.51.100.1    │   ✗   │  ← Route changed!
│ 4 │ 8.8.8.8         │ 8.8.8.8         │   ✓   │
╰───┴─────────────────┴─────────────────┴───────╯

Found 1 differences
```

---

### Test 9: Stats Command ⭐

**Purpose**: Quick trace statistics

```bash
tracemap stats test_trace.json
```

**Expected**:
```
Trace Statistics: google.com

Total hops: 12
Responded: 10
Timeouts: 2
Average RTT: 15.3ms
Max RTT: 45.2ms
Average Loss: 5.0%

Geo Coverage:
  - Hops with geo: 8/10 (80%)
  - ASN enrichment: 7/10 (70%)
```

---

### Test 10: Doctor Command ⭐

**Purpose**: System diagnostic

```bash
tracemap doctor
```

**Expected**:
```
Tracemap Doctor

✓ traceroute found: /usr/sbin/traceroute
  GeoIP not configured; will use API lookups
  ASN database not found (optional)
✓ Cache database: ~/.tracemap/cache.sqlite
  - Valid entries: 12
  - Hit rate: 85.3%

All checks passed!
```

---

## 🎯 Advanced Testing

### Test with Different Targets

```bash
# Test various targets
tracemap trace 1.1.1.1           # Cloudflare
tracemap trace 8.8.8.8           # Google DNS
tracemap trace github.com        # Complex routing
tracemap trace example.com       # Simple site
```

### Test Edge Cases

```bash
# Test timeouts
tracemap trace 192.0.2.1 --max-hops 5
# (bogus IP, should timeout cleanly)

# Test private profile with no MMDB
tracemap trace --profile private google.com
# Should work (no external calls)

# Test offline profile WITHOUT MMDB (should fail)
tracemap trace --profile offline google.com
# Expected: Error about missing MMDB

# Test with MMDB (if you have it)
tracemap trace --profile offline --geoip-mmdb ~/GeoLite2.mmdb google.com
```

---

## ✅ Final Verification Checklist

After testing, verify:

- [ ] Basic trace works and generates files
- [ ] Cache speeds up repeated traces (3-4x faster)
- [ ] Privacy profiles prevent external calls
- [ ] Watch mode updates continuously
- [ ] ECMP detection finds multiple paths
- [ ] HTML export opens in browser
- [ ] SVG export renders correctly
- [ ] Markdown export is readable
- [ ] TUI is interactive and navigable
- [ ] Replay shows saved traces
- [ ] Diff detects route changes
- [ ] Stats shows accurate metrics
- [ ] Doctor passes all checks

---

## 🐛 Troubleshooting

### Common Issues

**"traceroute not found"**
```bash
# macOS - should be built-in
which traceroute
# If missing, reinstall Xcode CLI tools
```

**"Cache database error"**
```bash
# Clear and recreate
tracemap cache clear
rm ~/.tracemap/cache.sqlite
# Run a trace to recreate
tracemap trace google.com
```

**"No geo data"**
```bash
# API might be rate-limited
# Use offline mode or wait
tracemap trace --profile private google.com
```

**"Permission denied"**
```bash
# Some protocols need sudo
sudo tracemap trace --protocol icmp google.com
```

---

## 📊 Testing Summary Template

After completing all tests, fill out:

```
# My Testing Results

Date: ___________
Version: 0.3.0

✓ = Pass | ✗ = Fail | ⚠️ = Partial

[ ] Basic trace
[ ] Caching (speedup observed)
[ ] Privacy profiles
[ ] Watch mode
[ ] ECMP detection
[ ] HTML export
[ ] SVG export
[ ] Markdown export
[ ] TUI mode
[ ] Replay/Diff
[ ] Stats command
[ ] Doctor command

Issues found:
- 
- 

Notes:
- 
- 
```

---

**Status**: Ready for comprehensive local testing!  
**Duration**: 20-30 minutes for full walkthrough  
**Result**: Production-ready confirmation
