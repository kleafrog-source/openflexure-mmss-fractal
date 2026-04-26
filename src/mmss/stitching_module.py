"""
Helpers for stitching selected gallery sessions into a single mosaic.
"""
from __future__ import annotations

import html
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def _walk_dict_for_xy(node: Any) -> tuple[float, float] | None:
    if isinstance(node, dict):
        keys = {str(key).lower(): key for key in node.keys()}
        if "x" in keys and "y" in keys:
            try:
                return float(node[keys["x"]]), float(node[keys["y"]])
            except Exception:
                pass
        for value in node.values():
            result = _walk_dict_for_xy(value)
            if result is not None:
                return result
    elif isinstance(node, list):
        for value in node:
            result = _walk_dict_for_xy(value)
            if result is not None:
                return result
    return None


def _walk_dict_for_matrix(node: Any) -> list[list[float]] | None:
    if isinstance(node, list) and len(node) == 2 and all(isinstance(row, list) for row in node):
        if all(len(row) >= 2 for row in node):
            try:
                return [
                    [float(node[0][0]), float(node[0][1])],
                    [float(node[1][0]), float(node[1][1])],
                ]
            except Exception:
                return None
    if isinstance(node, dict):
        for value in node.values():
            result = _walk_dict_for_matrix(value)
            if result is not None:
                return result
    elif isinstance(node, list):
        for value in node:
            result = _walk_dict_for_matrix(value)
            if result is not None:
                return result
    return None


def _extract_stage_position(context: dict[str, Any]) -> tuple[float, float] | None:
    for key in ("instrument_state", "instrument_settings", "stage_position"):
        value = context.get(key)
        result = _walk_dict_for_xy(value)
        if result is not None:
            return result
    return None


def _extract_csm_matrix(context: dict[str, Any]) -> list[list[float]] | None:
    for key in ("camera_stage_mapping", "instrument_settings", "instrument_state"):
        value = context.get(key)
        result = _walk_dict_for_matrix(value)
        if result is not None:
            return result
    return None


def _render_stitch_viewer(title: str, image_rel_path: str, stitch_meta: dict[str, Any]) -> str:
    raw_meta = html.escape(json.dumps(stitch_meta, indent=2, ensure_ascii=False))
    session_items = "".join(
        f"<li>{html.escape(session_id)}</li>"
        for session_id in stitch_meta.get("session_ids", [])
    )
    warning = stitch_meta.get("warning")
    warning_html = (
        f'<p style="color:#9a4624;"><strong>Warning:</strong> {html.escape(str(warning))}</p>'
        if warning else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: "Segoe UI", sans-serif; background: #f6f1e8; color: #1f1c17; }}
    .shell {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
    .panel {{ background: rgba(255,255,255,0.86); border: 1px solid rgba(0,0,0,0.08); border-radius: 20px; padding: 18px; margin-bottom: 16px; }}
    h1 {{ margin: 0 0 8px; font-family: Georgia, serif; }}
    img {{ width: 100%; display: block; border-radius: 16px; background: white; }}
    ul {{ margin: 0; padding-left: 18px; }}
    pre {{ overflow: auto; background: #1f1c17; color: #f6f1e8; padding: 14px; border-radius: 14px; }}
    a {{ color: #195c59; font-weight: 700; }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel">
      <h1>{html.escape(title)}</h1>
      <p>Stitched from {len(stitch_meta.get("session_ids", []))} selected gallery images.</p>
      {warning_html}
      <p><a href="../gallery/index.html">Back to gallery</a></p>
    </section>
    <section class="panel">
      <img src="{html.escape(image_rel_path)}" alt="Stitched microscope mosaic">
    </section>
    <section class="panel">
      <h2>Source Sessions</h2>
      <ul>{session_items}</ul>
    </section>
    <section class="panel">
      <h2>Metadata</h2>
      <pre>{raw_meta}</pre>
    </section>
  </main>
</body>
</html>
"""


class StitchingModule:
    """Create a stitched mosaic from selected gallery sessions."""

    def __init__(self, sessions_root: Path, output_root: Path):
        self.sessions_root = Path(sessions_root)
        self.output_root = Path(output_root)
        self.stitches_root = self.output_root / "stitches"
        self.stitches_root.mkdir(parents=True, exist_ok=True)

    def stitch_sessions(self, session_ids: list[str], overlap_percent: float = 15.0) -> dict[str, Any]:
        if len(session_ids) < 2:
            raise ValueError("Select at least two sessions for stitching.")

        from openflexure_stitching.loading.image import CachedOFSImage
        from openflexure_stitching.loading.image_sets import CachedOFSImageSet, OFSImageSet
        from openflexure_stitching.pipeline import perform_stitch_from_stage
        from openflexure_stitching.settings import OutputSettings

        stitch_id = "stitch_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        stitch_dir = self.stitches_root / stitch_id
        input_dir = stitch_dir / "inputs"
        stitch_dir.mkdir(parents=True, exist_ok=True)
        input_dir.mkdir(parents=True, exist_ok=True)

        cached_images: dict[str, CachedOFSImage] = {}
        source_info: list[dict[str, Any]] = []
        warning: str | None = None
        fallback_stride = None

        for index, session_id in enumerate(session_ids):
            session_dir = self.sessions_root / session_id
            manifest_path = session_dir / "session_manifest.json"
            report_path = session_dir / "report.json"
            if not manifest_path.exists() or not report_path.exists():
                raise FileNotFoundError(f"Missing session files for {session_id}")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            image_path = self.output_root.parent / manifest["image_path"]
            if not image_path.exists():
                raise FileNotFoundError(f"Missing image for {session_id}: {image_path}")

            target_name = f"{index:03d}_{Path(manifest['image_filename']).name}"
            target_path = input_dir / target_name
            shutil.copy2(image_path, target_path)

            with Image.open(target_path) as img:
                width, height = img.size

            microscope_context = report.get("session", {}).get("microscope_context") or report.get("microscope_context") or {}
            stage_position = _extract_stage_position(microscope_context)
            csm_matrix = _extract_csm_matrix(microscope_context)

            if stage_position is None:
                if fallback_stride is None:
                    fallback_stride = int(width * (1 - overlap_percent / 100.0))
                stage_position = (index * fallback_stride, 0)
                warning = "Some sessions had no recorded stage coordinates. A left-to-right fallback layout was used."

            if csm_matrix is None:
                csm_matrix = [[1.0, 0.0], [0.0, 1.0]]

            cached_images[target_name] = CachedOFSImage(
                filename=target_name,
                width=width,
                height=height,
                exif_available=False,
                usercomment_available=False,
                file_created_time=target_path.stat().st_mtime,
                file_size=target_path.stat().st_size,
                from_openflexure=False,
                capture_time=target_path.stat().st_mtime,
                stage_position=(int(stage_position[0]), int(stage_position[1])),
                camera_to_sample_matrix=np.array(csm_matrix),
                csm_width=width,
                pixel_size_um=1.0,
            )
            source_info.append(
                {
                    "session_id": session_id,
                    "image": target_name,
                    "stage_position": stage_position,
                    "csm_matrix": csm_matrix,
                }
            )

        cache = CachedOFSImageSet(images=cached_images)
        image_set = OFSImageSet(str(input_dir), cached=cache)
        perform_stitch_from_stage(image_set, OutputSettings(output_dir=str(stitch_dir), stitching_mode="stage_stitch"))

        stitched_image = stitch_dir / "stitched_from_stage.jpg"
        if not stitched_image.exists():
            raise RuntimeError("Stitching completed without producing stitched_from_stage.jpg")

        manifest = {
            "stitch_id": stitch_id,
            "session_ids": session_ids,
            "source_info": source_info,
            "warning": warning,
            "created_at": datetime.now().isoformat(),
            "stitched_image": f"stitches/{stitch_id}/stitched_from_stage.jpg",
            "viewer_path": f"stitches/{stitch_id}/index.html",
        }
        (stitch_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        (stitch_dir / "index.html").write_text(
            _render_stitch_viewer(
                title=f"Stitched Mosaic {stitch_id}",
                image_rel_path="stitched_from_stage.jpg",
                stitch_meta=manifest,
            ),
            encoding="utf-8",
        )

        return manifest
