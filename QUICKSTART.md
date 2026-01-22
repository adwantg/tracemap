# 🚀 Quick Start Guide - Running Tracemap Locally

## Prerequisites

- **Python 3.10+** (check your version: `python --version`)
- **traceroute** installed (macOS: built-in, Linux: `sudo apt install traceroute`)

## Step-by-Step Installation

### 1. Navigate to the Project Directory

```bash
cd /Users/goutamadwant/Documents/OpenSource/PythonProjects/traceroute-map-tui
```

### 2. Create and Activate Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
# .venv\Scripts\activate
```

### 3. Install the Package in Development Mode

```bash
# Install with all dependencies
pip install -e ".[all]"

# Or minimal install (no GeoIP/ASN):
# pip install -e .
```

### 4. Verify Installation

```bash
# Check that tracemap is installed
tracemap doctor
```

You should see:
```
Tracemap Doctor

✓ traceroute found: /usr/bin/traceroute
  GeoIP not configured; will use MockGeoLocator.
```

## 🎯 Running Your First Trace

### Basic Usage

```bash
# Simple trace (uses mock geo data)
tracemap trace google.com
```

### With Interactive TUI

```bash
# Run trace and save
tracemap trace google.com --out mytrace.json

# Open in interactive TUI
tracemap tui mytrace.json

# Or combine: trace and immediately view in TUI
tracemap replay mytrace.json --tui
```

### TUI Keyboard Shortcuts

- `↑/↓` or `j/k`: Navigate hops
- `Enter`: Show detailed hop information
- `e`: Export to HTML
- `r`: Refresh display
- `q`: Quit

### Export to HTML

```bash
# Trace and auto-export HTML
tracemap trace example.com

# HTML file will be at: .tracemap/trace.html
# Open in browser:
open .tracemap/trace.html
```

### Advanced Options

```bash
# Use TCP protocol instead of UDP
tracemap trace example.com --protocol tcp

# Enable ASN lookups
tracemap trace example.com --asn

# Customize hop count and timeout
tracemap trace example.com --max-hops 20 --timeout 3

# Privacy mode (redact IPs)
tracemap trace example.com --redact
```

## 📊 Other Useful Commands

### Compare Two Traces

```bash
# Run two traces at different times
tracemap trace example.com --out trace1.json
# ... wait a while ...
tracemap trace example.com --out trace2.json

# Compare them
tracemap diff trace1.json trace2.json
```

### View Statistics

```bash
tracemap stats .tracemap/trace.json
```

### Export Formats

```bash
# Export to interactive HTML
tracemap export .tracemap/trace.json --format html --out mymap.html

# Export to SVG (static image)
tracemap export .tracemap/trace.json --format svg --out mymap.svg
```

## 🔧 Optional: GeoIP Setup (for accurate locations)

1. **Create MaxMind Account**: https://www.maxmind.com/en/geolite2/signup
2. **Download GeoLite2 City database** (MMDB format)
3. **Set environment variable**:

```bash
export TRACEMAP_GEOIP_MMDB=/path/to/GeoLite2-City.mmdb

# Or pass as CLI flag:
tracemap trace google.com --geoip-mmdb /path/to/GeoLite2-City.mmdb
```

## 🐛 Troubleshooting

### "traceroute binary not found"

```bash
# macOS: already installed
# Linux:
sudo apt install traceroute
# or
sudo yum install traceroute
```

### "ModuleNotFoundError: No module named 'tracemap_tui'"

```bash
# Reinstall the package
cd /Users/goutamadwant/Documents/OpenSource/PythonProjects/traceroute-map-tui
pip install -e . --force-reinstall
```

### Permission Issues on Linux

Some systems require sudo for raw socket access:

```bash
# Run with sudo
sudo tracemap trace example.com

# Or give traceroute capabilities:
sudo setcap cap_net_raw+ep $(which tracemap)
```

## 📝 Example Session

```bash
# 1. Doctor check
tracemap doctor

# 2. Run a trace
tracemap trace google.com

# Output will show:
# - Live map updating as hops are discovered
# - Final map with all hops
# - Saved JSON at .tracemap/trace.json
# - Saved HTML at .tracemap/trace.html

# 3. View in browser
open .tracemap/trace.html

# 4. Launch interactive TUI
tracemap tui .tracemap/trace.json

# 5. Get stats
tracemap stats .tracemap/trace.json
```

## 🎨 What You'll See

**Terminal Output:**
- ASCII world map with hop markers (1, 2, 3...)
- Color-coded RTT indicators
- Detour alerts for unusual routes
- Hop table with IP, RTT, loss, location

**HTML Export (Interactive):**
- OpenStreetMap base layer
- Click markers for detailed hop info
- Color-coded by latency
- Shareable single HTML file

**TUI (Textual):**
- Split-panel layout
- Real-time hop table
- Map panel with paths
- Summary with alerts

##Deactivate Virtual Environment

When you're done:

```bash
deactivate
```

---

**Need Help?** Check the main [README.md](README.md) for full documentation!
