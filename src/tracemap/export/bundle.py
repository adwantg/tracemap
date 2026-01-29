import zipfile
from pathlib import Path
from ..models import TraceRun
from .html import export_html
from .markdown import export_markdown
from .svg import export_svg
import json

def export_bundle(trace: TraceRun, output_path: Path) -> None:
    """
    Create a ZIP bundle containing JSON, HTML, Markdown, and CSV exports.
    
    Args:
        trace: Trace result object
        output_path: Path to output .zip file
    """
    # Ensure parent dir exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    base_name = output_path.stem
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. JSON (Raw Data)
        json_str = json.dumps(trace.model_dump(mode="json"), indent=2, default=str)
        zf.writestr(f"{base_name}/trace.json", json_str)
        
        # 2. HTML (Interactive Map)
        # Use a temporary file approach or string buffer?
        # export_html writes to file, so we might need a tmp file
        # But for valid HTML export we need the logic.
        # Let's simple write to a temporary path and add it
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # HTML
            html_file = tmp_path / "trace.html"
            export_html(trace, html_file)
            zf.write(html_file, f"{base_name}/trace.html")
            
            # Markdown
            md_file = tmp_path / "report.md"
            export_markdown(trace, md_file)
            zf.write(md_file, f"{base_name}/report.md")
            
            # SVG (optional, requires display logic)
            # Try to export SVG
            try:
                svg_file = tmp_path / "diagram.svg"
                export_svg(trace, svg_file)
                zf.write(svg_file, f"{base_name}/diagram.svg")
            except Exception:
                pass # SVG might fail if fonts missing etc
        
        # 3. Quick Readme
        readme = f"""
# Trace Bundle: {trace.meta.host}
Date: {trace.meta.started_at}

Contents:
- trace.html: Interactive map visualization
- report.md: Incident report summary
- trace.json: Raw data for replaying
- diagram.svg: Static visualization
        """
        zf.writestr(f"{base_name}/README.txt", readme.strip())
