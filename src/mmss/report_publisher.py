"""
Utilities for packaging MMSS analysis outputs into browser-friendly reports.
"""
from __future__ import annotations

import html
import json
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "output"
SESSIONS_ROOT = OUTPUT_ROOT / "sessions"
GALLERY_ROOT = OUTPUT_ROOT / "gallery"
LATEST_ROOT = OUTPUT_ROOT / "latest"
RESULT_STREAMER_ROOT = OUTPUT_ROOT / "result_streamer"


def slugify(value: str) -> str:
    """Create a filesystem-safe slug."""
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {"-", "_"}:
            allowed.append(char)
        else:
            allowed.append("-")
    slug = "".join(allowed).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "session"


def _parse_timestamp(value: str | None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now()


def _safe_relpath(path: Path, start: Path) -> str:
    return path.resolve().relative_to(start.resolve()).as_posix()


def _extract_microscopy_advice(results: Dict[str, Any]) -> Dict[str, Any]:
    for iteration in results.get("iterations", []):
        advice = iteration.get("mmss_atoms", {}).get("microscopy_advice")
        if advice:
            return advice
    return {}


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "n/a"
    return str(value)


def _build_metric_cards(metrics: Dict[str, Any]) -> str:
    cards = []
    for key, value in metrics.items():
        cards.append(
            f"""
            <article class="metric-card">
              <div class="metric-label">{html.escape(str(key))}</div>
              <div class="metric-value">{html.escape(_format_metric(value))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _build_advice_list(advice: Dict[str, Any]) -> str:
    if not advice:
        return '<li>No microscopy advice generated for this run.</li>'

    items = []
    for key, value in advice.items():
        items.append(f"<li><strong>{html.escape(str(key))}:</strong> {html.escape(str(value))}</li>")
    return "\n".join(items)


def _build_vision_list(vision: Dict[str, Any], vision_status: str | None = None, vision_error: str | None = None) -> str:
    if not vision:
        if vision_error:
            return f"<li><strong>status:</strong> {html.escape(str(vision_status or 'unavailable'))}</li><li><strong>error:</strong> {html.escape(str(vision_error))}</li>"
        return '<li>No raw Mistral vision summary for this session.</li>'

    preferred_order = [
        "object_guess",
        "focus_quality",
        "focus_guess",
        "category_guess",
        "confidence",
        "summary",
        "biological_interpretation",
        "fractal_character",
        "visible_structures",
        "recommended_followup",
        "model",
        "mode",
    ]
    seen = set()
    items = []
    for key in preferred_order + [k for k in vision.keys() if k not in preferred_order]:
        if key in seen or key not in vision:
            continue
        seen.add(key)
        value = vision[key]
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        items.append(f"<li><strong>{html.escape(str(key))}:</strong> {html.escape(str(value))}</li>")
    return "\n".join(items)


def _build_iteration_blocks(iterations: list[Dict[str, Any]]) -> str:
    if not iterations:
        return "<p>No iteration history recorded.</p>"

    blocks = []
    for iteration in iterations:
        atoms = iteration.get("mmss_atoms", {})
        mistral = iteration.get("mistral_response", {})
        block = f"""
        <section class="iteration-card">
          <div class="iteration-header">
            <h3>Iteration {iteration.get("iteration", "?")}</h3>
            <span>{html.escape(str(iteration.get("timestamp", "n/a")))}</span>
          </div>
          <div class="iteration-grid">
            <div>
              <h4>Detected Pattern</h4>
              <p>{html.escape(str(atoms.get("detected_type", "No confident match")))}</p>
            </div>
            <div>
              <h4>Suggested Command</h4>
              <p>{html.escape(str(mistral.get("command", "n/a")))}</p>
            </div>
            <div>
              <h4>Formula</h4>
              <p class="formula-small">{html.escape(str(iteration.get("formula", "n/a")))}</p>
            </div>
            <div>
              <h4>Core Metrics</h4>
              <p>V={html.escape(_format_metric(atoms.get("V")))}, S={html.escape(_format_metric(atoms.get("S")))}, D_f={html.escape(_format_metric(atoms.get("D_f")))}, R_T={html.escape(_format_metric(atoms.get("R_T")))}</p>
            </div>
          </div>
        </section>
        """
        blocks.append(block)
    return "\n".join(blocks)


def _render_session_html(session_meta: Dict[str, Any], results: Dict[str, Any]) -> str:
    metrics = session_meta.get("final_metrics", {})
    advice = session_meta.get("microscopy_advice", {})
    final_formula = session_meta.get("final_formula") or "No final formula available"
    final_type = metrics.get("detected_type", "Unknown pattern")
    timestamp = session_meta.get("timestamp", "n/a")
    status = session_meta.get("status", "unknown")
    vision_analysis = session_meta.get("vision_analysis", {})
    vision_status = session_meta.get("vision_status")
    vision_error = session_meta.get("vision_error")
    raw_json = html.escape(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Check which analysis modes are available
    has_invariants = results.get("invariants_analysis") is not None
    has_hybrid = results.get("hybrid_analysis") is not None
    has_vision_only = results.get("vision_only_analysis") is not None
    
    # Build mode indicators
    mode_indicators = []
    if has_invariants:
        mode_indicators.append('<span class="mode-tag mode-invariants">Invariants ✓</span>')
    if has_hybrid:
        mode_indicators.append('<span class="mode-tag mode-hybrid">Hybrid ✓</span>')
    if has_vision_only:
        mode_indicators.append('<span class="mode-tag mode-vision">Vision Only ✓</span>')
    
    mode_indicators_html = " ".join(mode_indicators) if mode_indicators else '<span class="mode-tag mode-none">No analysis modes</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MMSS Analysis Viewer</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: rgba(255, 252, 246, 0.84);
      --ink: #1f1c17;
      --muted: #665f55;
      --accent: #b6542a;
      --accent-2: #195c59;
      --line: rgba(31, 28, 23, 0.1);
      --shadow: 0 24px 60px rgba(35, 23, 10, 0.12);
      --radius: 24px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(182, 84, 42, 0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(25, 92, 89, 0.18), transparent 32%),
        linear-gradient(180deg, #f7f1e8 0%, #efe6d8 100%);
    }}
    .shell {{
      width: min(1280px, calc(100% - 32px));
      margin: 24px auto 48px;
      display: grid;
      gap: 24px;
    }}
    .hero, .panel {{
      background: var(--panel);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.6);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 28px;
      display: grid;
      gap: 18px;
    }}
    .hero-top {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      flex-wrap: wrap;
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 12px;
      color: var(--accent-2);
      margin-bottom: 10px;
      font-weight: 700;
    }}
    h1, h2, h3, h4 {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-weight: 700;
    }}
    h1 {{
      font-size: clamp(34px, 4vw, 54px);
      line-height: 0.95;
      max-width: 12ch;
    }}
    .hero p {{
      margin: 10px 0 0;
      max-width: 72ch;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.5;
    }}
    .status-pill {{
      border-radius: 999px;
      padding: 10px 16px;
      background: rgba(25, 92, 89, 0.1);
      color: var(--accent-2);
      font-weight: 700;
      border: 1px solid rgba(25, 92, 89, 0.16);
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 24px;
    }}
    .image-wrap {{
      overflow: hidden;
      border-radius: 20px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.5);
      min-height: 320px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .image-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }}
    .side-stack {{
      display: grid;
      gap: 16px;
    }}
    .formula-box {{
      padding: 18px;
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(182, 84, 42, 0.10), rgba(25, 92, 89, 0.08));
      border: 1px solid rgba(182, 84, 42, 0.18);
    }}
    .formula-box code {{
      display: block;
      white-space: pre-wrap;
      font-size: 15px;
      line-height: 1.5;
      color: var(--ink);
      font-family: "Consolas", "Courier New", monospace;
    }}
    .meta-list, .advice-list {{
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
    }}
    .panel {{
      padding: 24px;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 14px;
      margin-top: 16px;
    }}
    .metric-card {{
      border-radius: 18px;
      padding: 16px;
      background: rgba(255, 255, 255, 0.55);
      border: 1px solid var(--line);
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .metric-value {{
      font-size: 26px;
      font-weight: 700;
    }}
    .iteration-stack {{
      display: grid;
      gap: 16px;
      margin-top: 16px;
    }}
    .iteration-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.48);
    }}
    .iteration-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}
    .iteration-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    .iteration-grid p {{
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .formula-small {{
      font-family: "Consolas", "Courier New", monospace;
      font-size: 13px;
    }}
    details {{
      margin-top: 18px;
      border-top: 1px solid var(--line);
      padding-top: 18px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 700;
    }}
    pre {{
      overflow: auto;
      padding: 16px;
      border-radius: 16px;
      background: #1f1c17;
      color: #f7f1e8;
      font-size: 13px;
      line-height: 1.5;
    }}
    .footer-link {{
      color: var(--accent-2);
      text-decoration: none;
      font-weight: 700;
    }}
    @media (max-width: 920px) {{
      .summary-grid {{
        grid-template-columns: 1fr;
      }}
      .shell {{
        width: min(100% - 18px, 1280px);
      }}
    }}
    .mode-tags {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .mode-tag {{
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 700;
    }}
    .mode-invariants {{
      background: rgba(25, 92, 89, 0.12);
      color: var(--accent-2);
    }}
    .mode-hybrid {{
      background: rgba(108, 67, 156, 0.12);
      color: #6c439c;
    }}
    .mode-vision {{
      background: rgba(182, 84, 42, 0.12);
      color: var(--accent);
    }}
    .mode-none {{
      background: rgba(102, 95, 85, 0.12);
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-top">
        <div>
          <div class="eyebrow">MMSS Fractal Analysis</div>
          <h1>{html.escape(str(final_type))}</h1>
          <p>Captured at {html.escape(str(timestamp))}. This viewer groups the microscope image, JSON report, and the final MMSS decision into one session so it can be opened directly in a browser on the workstation or microscope display.</p>
          <div class="mode-tags">{mode_indicators_html}</div>
        </div>
        <div class="status-pill">{html.escape(str(status)).upper()}</div>
      </div>

      <div class="summary-grid">
        <div class="image-wrap">
          <img src="{html.escape(session_meta['image_filename'])}" alt="Microscope capture">
        </div>

        <div class="side-stack">
          <div class="formula-box">
            <div class="eyebrow">Final Formula</div>
            <code>{html.escape(str(final_formula))}</code>
          </div>

          <div class="panel">
            <div class="eyebrow">Microscope Advice</div>
            <ul class="advice-list">
              {_build_advice_list(advice)}
            </ul>
          </div>

            <div class="panel">
              <div class="eyebrow">Mistral Raw Vision</div>
            <ul class="advice-list">
              {_build_vision_list(vision_analysis, vision_status, vision_error)}
            </ul>
          </div>

          <div class="panel">
            <div class="eyebrow">Session Files</div>
            <ul class="meta-list">
              <li>Image: {html.escape(session_meta['image_filename'])}</li>
              <li>JSON: {html.escape(session_meta['report_filename'])}</li>
              <li>Viewer: index.html</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="eyebrow">Final Metrics</div>
      <div class="metric-grid">
        {_build_metric_cards(metrics)}
      </div>
    </section>

    <section class="panel">
      <div class="eyebrow">Iteration History</div>
      <div class="iteration-stack">
        {_build_iteration_blocks(results.get("iterations", []))}
      </div>
    </section>

    <section class="panel">
      <div class="eyebrow">Raw Report</div>
      <p style="color: var(--muted); margin-top: 0;">For debugging or exporting, the full JSON is embedded below and also saved next to the image.</p>
      <details>
        <summary>Show JSON payload</summary>
        <pre>{raw_json}</pre>
      </details>
      <p><a class="footer-link" href="../../gallery/index.html">Open report gallery</a></p>
    </section>
  </main>
</body>
</html>
"""


def _render_gallery_html(sessions: list[Dict[str, Any]]) -> str:
    cards = []
    for session in sessions:
        metrics = session.get("final_metrics", {})
        detected = metrics.get("detected_type", "Unknown pattern")
        
        # Check which analysis modes are available
        has_invariants = session.get("has_invariants", False)
        has_hybrid = session.get("has_hybrid", False)
        has_vision_only = session.get("has_vision_only", False)
        
        invariants_status = "✓" if has_invariants else "—"
        hybrid_status = "✓" if has_hybrid else "—"
        vision_status = "✓" if has_vision_only else "—"
        
        cards.append(
            f"""
            <div class="card" data-session-id="{html.escape(session['session_id'])}" data-image-path="{html.escape(session.get('image_path', ''))}">
              <label class="card-checkbox">
                <input type="checkbox" class="session-checkbox" value="{html.escape(session['session_id'])}">
                <span class="checkmark"></span>
              </label>
              <a href="../sessions/{html.escape(session['session_id'])}/index.html" class="card-link">
                <img src="../sessions/{html.escape(session['session_id'])}/{html.escape(session['image_filename'])}" alt="Capture preview">
                <div class="card-body">
                  <div class="stamp">{html.escape(str(session.get('timestamp', 'n/a')))}</div>
                  <h2>{html.escape(str(detected))}</h2>
                  <p>{html.escape(str(session.get('final_formula') or 'No final formula'))}</p>
                  <div class="chip-row">
                    <span>V {html.escape(_format_metric(metrics.get('V')))}</span>
                    <span>D_f {html.escape(_format_metric(metrics.get('D_f')))}</span>
                    <span>Status {html.escape(str(session.get('status', 'unknown')))}</span>
                  </div>
                  <div class="mode-row">
                    <span class="mode-invariants">Invariants: {invariants_status}</span>
                    <span class="mode-hybrid">Hybrid: {hybrid_status}</span>
                    <span class="mode-vision">Vision: {vision_status}</span>
                  </div>
                </div>
              </a>
            </div>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MMSS Report Gallery</title>
  <style>
    :root {{
      --bg: #f7f4ee;
      --ink: #201a14;
      --muted: #655d52;
      --accent: #195c59;
      --card: rgba(255,255,255,0.78);
      --line: rgba(32,26,20,0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(182, 84, 42, 0.12), transparent 26%),
        radial-gradient(circle at top right, rgba(25, 92, 89, 0.16), transparent 34%),
        linear-gradient(180deg, #fbf8f2 0%, #f0e9dd 100%);
    }}
    .shell {{
      width: min(1320px, calc(100% - 32px));
      margin: 28px auto 48px;
    }}
    h1 {{
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(34px, 5vw, 64px);
      line-height: 0.95;
      margin: 0 0 10px;
    }}
    .lede {{
      max-width: 72ch;
      color: var(--muted);
      line-height: 1.6;
      margin-bottom: 28px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
    }}
    .card {{
      display: block;
      text-decoration: none;
      color: inherit;
      border: 1px solid rgba(255,255,255,0.7);
      background: var(--card);
      border-radius: 24px;
      overflow: hidden;
      box-shadow: 0 22px 56px rgba(31, 28, 23, 0.12);
      transition: transform 120ms ease, box-shadow 120ms ease;
    }}
    .card:hover {{
      transform: translateY(-4px);
      box-shadow: 0 28px 72px rgba(31, 28, 23, 0.16);
    }}
    .card img {{
      width: 100%;
      height: 220px;
      object-fit: cover;
      display: block;
      background: #ddd5c8;
    }}
    .card-body {{
      padding: 18px;
    }}
    .stamp {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    h2 {{
      margin: 0 0 8px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 28px;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}
    .chip-row span {{
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(25, 92, 89, 0.08);
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
    }}
    .raw-vision-status {{
      background: rgba(182, 84, 42, 0.12);
      color: #b6542a;
    }}
    .mode-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .mode-row span {{
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
    }}
    .mode-invariants {{
      background: rgba(25, 92, 89, 0.12);
      color: var(--accent);
    }}
    .mode-hybrid {{
      background: rgba(108, 67, 156, 0.12);
      color: #6c439c;
    }}
    .mode-vision {{
      background: rgba(182, 84, 42, 0.12);
      color: #b6542a;
    }}
    .card {{
      position: relative;
    }}
    .card-checkbox {{
      position: absolute;
      top: 12px;
      left: 12px;
      z-index: 10;
      cursor: pointer;
    }}
    .card-checkbox input {{
      display: none;
    }}
    .checkmark {{
      display: block;
      width: 24px;
      height: 24px;
      border: 2px solid var(--accent);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.9);
      transition: all 150ms ease;
    }}
    .card-checkbox input:checked + .checkmark {{
      background: var(--accent);
      border-color: var(--accent);
    }}
    .card-checkbox input:checked + .checkmark::after {{
      content: "✓";
      display: block;
      color: white;
      text-align: center;
      line-height: 20px;
      font-size: 14px;
      font-weight: bold;
    }}
    .card-link {{
      display: block;
      text-decoration: none;
      color: inherit;
    }}
    .batch-controls {{
      margin: 24px 0;
      padding: 16px;
      background: var(--card);
      border-radius: 16px;
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .batch-controls button {{
      padding: 12px 24px;
      background: var(--accent);
      color: white;
      border: none;
      border-radius: 999px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      transition: background 150ms ease;
    }}
    .batch-controls button:hover {{
      background: #144a47;
    }}
    .batch-controls button:disabled {{
      background: var(--muted);
      cursor: not-allowed;
    }}
    .batch-controls .btn-invariants {{
      background: var(--accent);
    }}
    .batch-controls .btn-invariants:hover {{
      background: #144a47;
    }}
    .batch-controls .btn-hybrid {{
      background: #6c439c;
    }}
    .batch-controls .btn-hybrid:hover {{
      background: #5a3585;
    }}
    .batch-controls .btn-vision {{
      background: #b6542a;
    }}
    .batch-controls .btn-vision:hover {{
      background: #9a4624;
    }}
    .batch-status {{
      color: var(--muted);
      font-size: 14px;
    }}
    .batch-progress {{
      width: 100%;
      max-width: 300px;
      height: 8px;
      background: rgba(32, 26, 20, 0.1);
      border-radius: 999px;
      overflow: hidden;
    }}
    .batch-progress-bar {{
      height: 100%;
      background: var(--accent);
      width: 0%;
      transition: width 300ms ease;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <h1>Microscope Analysis Gallery</h1>
    <p class="lede">Each capture is stored as a session pair: microscope image, raw JSON report, and a browser-ready HTML viewer. Open any card to inspect the full MMSS decision trace.</p>
    
    <div class="batch-controls">
      <button class="btn-invariants" onclick="runBatchAnalysis('invariants')">Run Invariants on Selected</button>
      <button class="btn-hybrid" onclick="runBatchAnalysis('hybrid')">Run Hybrid on Selected</button>
      <button class="btn-vision" onclick="runBatchAnalysis('vision_only')">Run Vision Only on Selected</button>
      <span id="batchStatus" class="batch-status">Select images to analyze</span>
      <div class="batch-progress">
        <div id="batchProgressBar" class="batch-progress-bar"></div>
      </div>
    </div>
    
    <section class="grid">
      {"".join(cards) or "<p>No sessions published yet.</p>"}
    </section>
  </main>
  
  <script>
    async function runBatchAnalysis(mode) {{
      const checkboxes = document.querySelectorAll('.session-checkbox:checked');
      if (checkboxes.length === 0) {{
        alert('Please select at least one image');
        return;
      }}
      
      const buttons = document.querySelectorAll('.batch-controls button');
      const status = document.getElementById('batchStatus');
      const progressBar = document.getElementById('batchProgressBar');
      
      buttons.forEach(btn => btn.disabled = true);
      const sessionIds = Array.from(checkboxes).map(cb => cb.value);
      
      for (let i = 0; i < sessionIds.length; i++) {{
        const sessionId = sessionIds[i];
        status.textContent = `Processing ${{i + 1}}/${{sessionIds.length}} (${{mode}}): ${{sessionId}}`;
        progressBar.style.width = `${{((i + 1) / sessionIds.length) * 100}}%`;
        
        try {{
          const response = await fetch('/api/batch-analysis', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ session_id: sessionId, mode: mode }})
          }});
          
          if (response.ok) {{
            const result = await response.json();
            console.log('Analysis result:', result);
            // Update card status
            const card = document.querySelector(`[data-session-id="${{sessionId}}"]`);
            if (card) {{
              let statusClass = '';
              if (mode === 'invariants') statusClass = '.mode-invariants';
              else if (mode === 'hybrid') statusClass = '.mode-hybrid';
              else if (mode === 'vision_only') statusClass = '.mode-vision';
              
              const statusSpan = card.querySelector(statusClass);
              if (statusSpan) {{
                const modeName = mode === 'vision_only' ? 'Vision' : mode.charAt(0).toUpperCase() + mode.slice(1);
                statusSpan.textContent = `${{modeName}}: ✓`;
              }}
            }}
          }} else {{
            console.error('Analysis failed for', sessionId, mode);
          }}
        }} catch (error) {{
          console.error('Error processing', sessionId, mode, error);
        }}
        
        // 30 second delay between requests
        if (i < sessionIds.length - 1) {{
          await new Promise(resolve => setTimeout(resolve, 30000));
        }}
      }}
      
      status.textContent = `Completed ${{sessionIds.length}} images (${{mode}})`;
      buttons.forEach(btn => btn.disabled = false);
      setTimeout(() => location.reload(), 2000);
    }}
  </script>
</body>
</html>
"""


def _render_result_streamer_html(refresh_seconds: int = 5) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MMSS Result Streamer</title>
  <style>
    :root {{
      --bg: #efe7d9;
      --panel: rgba(255,255,255,0.78);
      --ink: #201a14;
      --muted: #6a6258;
      --accent: #195c59;
      --accent-warm: #b6542a;
      --line: rgba(32,26,20,0.1);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(182,84,42,0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(25,92,89,0.14), transparent 32%),
        linear-gradient(180deg, #f9f4ec 0%, #ece1d0 100%);
    }}
    .shell {{
      width: min(100vw, 1600px);
      margin: 0 auto;
      padding: 18px;
      display: grid;
      gap: 16px;
      min-height: 100vh;
    }}
    .topbar {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 18px;
      border-radius: 22px;
      background: var(--panel);
      border: 1px solid rgba(255,255,255,0.7);
      box-shadow: 0 18px 48px rgba(31, 28, 23, 0.10);
      align-items: center;
    }}
    .title-wrap h1 {{
      margin: 0;
      font-size: clamp(26px, 4vw, 44px);
      line-height: 0.95;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .title-wrap p {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}
    .pill {{
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(25,92,89,0.08);
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      border: 1px solid rgba(25,92,89,0.12);
    }}
    .link {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 700;
    }}
    .viewer-shell {{
      position: relative;
      flex: 1;
      min-height: calc(100vh - 132px);
      border-radius: 24px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.7);
      box-shadow: 0 22px 56px rgba(31, 28, 23, 0.12);
      background: rgba(255,255,255,0.55);
    }}
    iframe {{
      width: 100%;
      height: calc(100vh - 132px);
      border: 0;
      background: white;
    }}
    .empty-state {{
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      padding: 24px;
      text-align: center;
    }}
    .empty-card {{
      max-width: 680px;
      padding: 28px;
      border-radius: 24px;
      background: rgba(255,255,255,0.84);
      border: 1px solid var(--line);
    }}
    .empty-card h2 {{
      margin: 0 0 10px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(28px, 4vw, 46px);
    }}
    .empty-card p {{
      color: var(--muted);
      line-height: 1.6;
      margin: 0;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="topbar">
      <div class="title-wrap">
        <h1>MMSS Result Streamer</h1>
        <p>This page stays fixed and automatically refreshes to show the newest microscope analysis report.</p>
      </div>
      <div class="meta">
        <span class="pill" id="refresh-pill">Refresh: every {refresh_seconds}s</span>
        <span class="pill" id="session-pill">Waiting for first report</span>
        <a class="pill link" href="/gallery/index.html">Gallery</a>
      </div>
    </section>
    <section class="viewer-shell">
      <div class="empty-state" id="empty-state">
        <div class="empty-card">
          <h2>No report yet</h2>
          <p>As soon as a new microscope capture is analyzed, the latest report will appear here automatically without changing this page address.</p>
        </div>
      </div>
      <iframe id="report-frame" title="Latest MMSS report" hidden></iframe>
    </section>
  </main>
  <script>
    const manifestUrl = '/latest/session_manifest.json';
    const frame = document.getElementById('report-frame');
    const emptyState = document.getElementById('empty-state');
    const sessionPill = document.getElementById('session-pill');
    let currentSessionId = null;

    async function loadLatest(forceReload = false) {{
      try {{
        const response = await fetch(`${{manifestUrl}}?t=${{Date.now()}}`, {{ cache: 'no-store' }});
        if (!response.ok) {{
          throw new Error(`HTTP ${{response.status}}`);
        }}

        const manifest = await response.json();
        const nextSessionId = manifest.session_id || null;
        const target = manifest.stream_path || manifest.viewer_path || null;

        if (!nextSessionId || !target) {{
          throw new Error('No latest report metadata yet.');
        }}

        sessionPill.textContent = `Latest: ${{nextSessionId}}`;
        emptyState.hidden = true;
        frame.hidden = false;

        const normalizedTarget = '/' + target.replace(/^\\/+/, '');
        if (forceReload || currentSessionId !== nextSessionId) {{
          currentSessionId = nextSessionId;
          frame.src = `${{normalizedTarget}}?embed=1&t=${{Date.now()}}`;
        }} else if (frame.contentWindow) {{
          frame.contentWindow.location.reload();
        }}
      }} catch (error) {{
        sessionPill.textContent = 'Waiting for latest report';
        frame.hidden = true;
        emptyState.hidden = false;
      }}
    }}

    loadLatest(true);
    setInterval(() => loadLatest(false), {refresh_seconds * 1000});
  </script>
</body>
</html>
"""


def create_session_id(image_path: str | Path, results: Dict[str, Any]) -> str:
    image_name = Path(image_path).stem
    timestamp = _parse_timestamp(results.get("timestamp")).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{slugify(image_name)}"


def publish_analysis_session(image_path: str | Path, results: Dict[str, Any]) -> Dict[str, Any]:
    """Create a session folder with image, JSON, and browser-ready HTML."""
    source_image = Path(image_path).resolve()
    source_report = Path(results["report_path"]).resolve()

    if source_image.parent.parent == SESSIONS_ROOT.resolve():
        session_id = source_image.parent.name
        session_dir = source_image.parent
    else:
        session_id = create_session_id(source_image, results)
        session_dir = SESSIONS_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    session_image = session_dir / source_image.name
    if source_image != session_image:
        shutil.copy2(source_image, session_image)

    session_report = session_dir / "report.json"
    if source_report != session_report:
        shutil.copy2(source_report, session_report)

    has_invariants = results.get("invariants_analysis") is not None
    has_hybrid = results.get("hybrid_analysis") is not None
    has_vision_only = results.get("vision_only_analysis") is not None

    session_meta = {
        "session_id": session_id,
        "timestamp": results.get("timestamp"),
        "status": results.get("status"),
        "image_filename": session_image.name,
        "report_filename": session_report.name,
        "image_path": _safe_relpath(session_image, PROJECT_ROOT),
        "report_path": _safe_relpath(session_report, PROJECT_ROOT),
        "viewer_path": _safe_relpath(session_dir / "index.html", PROJECT_ROOT),
        "final_formula": results.get("final_formula"),
        "final_metrics": results.get("final_metrics", {}),
        "vision_analysis": results.get("vision_analysis") or {},
        "vision_status": results.get("vision_status"),
        "vision_error": results.get("vision_error") or results.get("last_analysis_error"),
        "microscopy_advice": _extract_microscopy_advice(results),
        "iterations_count": len(results.get("iterations", [])),
        "has_invariants": has_invariants,
        "has_hybrid": has_hybrid,
        "has_vision_only": has_vision_only,
    }

    session_payload = dict(results)
    session_payload["session"] = session_meta
    session_payload["report_path"] = session_meta["report_path"]

    session_report.write_text(
        json.dumps(session_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    session_manifest = session_dir / "session_manifest.json"
    session_manifest.write_text(
        json.dumps(session_meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    viewer_path = session_dir / "index.html"
    viewer_path.write_text(
        _render_session_html(session_meta, session_payload),
        encoding="utf-8",
    )

    build_gallery()

    latest_index = LATEST_ROOT / "index.html"
    latest_index.parent.mkdir(parents=True, exist_ok=True)
    latest_index.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url=../sessions/{session_id}/index.html">
  <title>Latest MMSS Report</title>
</head>
<body>
  <p>Redirecting to the latest report: <a href="../sessions/{session_id}/index.html">open viewer</a></p>
</body>
</html>
""",
        encoding="utf-8",
    )

    latest_manifest = dict(session_meta)
    latest_manifest["stream_path"] = "sessions/{}/index.html".format(session_id)
    (LATEST_ROOT / "session_manifest.json").write_text(
        json.dumps(latest_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    RESULT_STREAMER_ROOT.mkdir(parents=True, exist_ok=True)
    (RESULT_STREAMER_ROOT / "index.html").write_text(
        _render_result_streamer_html(),
        encoding="utf-8",
    )

    return {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "image_path": str(session_image),
        "report_path": str(session_report),
        "viewer_path": str(viewer_path),
        "latest_viewer_path": str(latest_index),
        "result_streamer_path": str(RESULT_STREAMER_ROOT / "index.html"),
    }


def build_gallery() -> str:
    """Build or refresh the global report gallery."""
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    GALLERY_ROOT.mkdir(parents=True, exist_ok=True)
    RESULT_STREAMER_ROOT.mkdir(parents=True, exist_ok=True)

    sessions = []
    for manifest_path in SESSIONS_ROOT.glob("*/session_manifest.json"):
        try:
            sessions.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue

    sessions.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

    gallery_path = GALLERY_ROOT / "index.html"
    gallery_path.write_text(_render_gallery_html(sessions), encoding="utf-8")
    (RESULT_STREAMER_ROOT / "index.html").write_text(
        _render_result_streamer_html(),
        encoding="utf-8",
    )
    return str(gallery_path)


def can_connect(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def ensure_report_server(port: int = 8765) -> str | None:
    """Start the static report server if it is not already running."""
    if can_connect(port):
        return f"http://127.0.0.1:{port}"

    script_path = PROJECT_ROOT / "serve_reports.py"
    command = [sys.executable, str(script_path), "--port", str(port), "--no-open"]
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=True,
        )
    except OSError:
        return None

    for _ in range(20):
        if can_connect(port):
            return f"http://127.0.0.1:{port}"
        time.sleep(0.2)

    return None


def build_viewer_targets(session_id: str, port: int = 8765) -> Dict[str, str]:
    base_url = f"http://127.0.0.1:{port}"
    local_ip = get_local_ip()
    return {
        "local_url": f"{base_url}/sessions/{session_id}/index.html",
        "lan_url": f"http://{local_ip}:{port}/sessions/{session_id}/index.html",
        "latest_local_url": f"{base_url}/latest/index.html",
        "gallery_local_url": f"{base_url}/gallery/index.html",
        "result_streamer_local_url": f"{base_url}/result_streamer/index.html",
        "result_streamer_lan_url": f"http://{local_ip}:{port}/result_streamer/index.html",
    }


def open_in_browser(target: str) -> bool:
    """Try to open a report page in the default browser."""
    try:
        return webbrowser.open(target)
    except Exception:
        return False
