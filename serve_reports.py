#!/usr/bin/env python
"""
Serve generated MMSS reports over HTTP for browser-based viewing.
"""
from __future__ import annotations

import argparse
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.mmss.env_utils import load_project_env
from src.mmss.report_publisher import (
    OUTPUT_ROOT,
    PROJECT_ROOT,
    SESSIONS_ROOT,
    build_gallery,
    get_local_ip,
    open_in_browser,
    publish_analysis_session,
)
from src.mmss.stitching_module import StitchingModule

load_project_env()


class APIHandler(SimpleHTTPRequestHandler):
    """Custom handler that serves static files and API endpoints."""

    @staticmethod
    def _resolve_project_path(value: str | None) -> Path | None:
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @staticmethod
    def _merge_analysis_result(existing_report: dict, analysis_result: dict, mode: str) -> dict:
        merged = dict(existing_report or {})
        core_fields = {
            "iterations",
            "final_formula",
            "final_metrics",
            "vision_analysis",
            "vision_status",
            "vision_error",
            "analysis_mode",
            "timestamp",
            "image_path",
            "report_path",
            "status",
            "last_update",
            "completion_time",
            "error",
            "error_time",
        }
        requires_real_vision = mode in {"hybrid", "vision_only"}
        has_useful_vision = bool(analysis_result.get("vision_analysis"))

        preserved_mode_blocks = {
            "invariants_analysis": existing_report.get("invariants_analysis"),
            "hybrid_analysis": existing_report.get("hybrid_analysis"),
            "vision_only_analysis": existing_report.get("vision_only_analysis"),
        }

        for key, value in analysis_result.items():
            if key == "session":
                continue
            if requires_real_vision and not has_useful_vision and key in core_fields:
                continue
            merged[key] = value

        merged.update(preserved_mode_blocks)

        if mode == "invariants":
            merged["invariants_analysis"] = analysis_result
        elif mode == "hybrid":
            merged["hybrid_analysis"] = analysis_result
        elif mode == "vision_only":
            merged["vision_only_analysis"] = analysis_result

        if requires_real_vision and not has_useful_vision:
            merged["last_analysis_error"] = analysis_result.get("vision_error") or "Mistral raw vision did not return data for this run."
        else:
            merged.pop("last_analysis_error", None)

        merged["analysis_mode_last_run"] = mode
        return merged
    
    def do_POST(self):
        """Handle POST requests for API endpoints."""
        if self.path == "/api/batch-analysis":
            self.handle_batch_analysis()
        elif self.path == "/api/stitch-selected":
            self.handle_stitch_selected()
        else:
            self.send_error(404, "API endpoint not found")
    
    def handle_batch_analysis(self):
        """Handle batch analysis request for any mode."""
        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))
            
            session_id = data.get("session_id")
            mode = data.get("mode", "invariants")
            
            if not session_id:
                self.send_error(400, "Missing session_id")
                return
            
            if mode not in ["invariants", "hybrid", "vision_only"]:
                self.send_error(400, "Invalid mode")
                return
            
            # Find session manifest
            manifest_path = SESSIONS_ROOT / session_id / "session_manifest.json"
            if not manifest_path.exists():
                self.send_error(404, "Session not found")
                return
            
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            image_path = self._resolve_project_path(manifest.get("image_path"))
            report_path = self._resolve_project_path(manifest.get("report_path"))
            
            if not image_path or not image_path.exists():
                self.send_error(404, "Image not found")
                return
            
            # Run analysis based on mode
            from src.mmss.mmss_engine import MMSS_Engine
            
            os.environ["USE_REAL_MICROSCOPE"] = "False"
            os.environ["MMSS_SAFETY_MODE_ACTIVE"] = "True"
            os.environ["MMSS_ANALYSIS_MODE"] = mode
            
            engine = MMSS_Engine(config={})

            analysis_result = engine.run(str(image_path))

            existing_report = {}
            if report_path and report_path.exists():
                with open(report_path, "r", encoding="utf-8") as f:
                    existing_report = json.load(f)

            merged_report = self._merge_analysis_result(existing_report, analysis_result, mode)
            published = publish_analysis_session(str(image_path), merged_report)
            build_gallery()
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "success": True,
                "mode": mode,
                "result": analysis_result,
                "session_id": published["session_id"],
                "viewer_path": published["viewer_path"],
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
            
        except Exception as e:
            print(f"Error in batch analysis: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def handle_stitch_selected(self):
        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))
            session_ids = data.get("session_ids") or []
            overlap_percent = float(data.get("overlap_percent", 15.0))

            stitcher = StitchingModule(SESSIONS_ROOT, OUTPUT_ROOT)
            manifest = stitcher.stitch_sessions(session_ids=session_ids, overlap_percent=overlap_percent)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "stitch": manifest}).encode("utf-8"))
        except Exception as e:
            print(f"Error in stitching: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))


def main():
    parser = argparse.ArgumentParser(description="Serve MMSS report gallery over HTTP")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8765, help="TCP port to serve")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()

    build_gallery()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    handler = partial(APIHandler, directory=str(Path(OUTPUT_ROOT)))
    server = ThreadingHTTPServer((args.host, args.port), handler)

    local_url = f"http://127.0.0.1:{args.port}/gallery/index.html"
    lan_url = f"http://{get_local_ip()}:{args.port}/gallery/index.html"
    streamer_local_url = f"http://127.0.0.1:{args.port}/result_streamer/index.html"
    streamer_lan_url = f"http://{get_local_ip()}:{args.port}/result_streamer/index.html"

    print(f"Serving MMSS reports from: {OUTPUT_ROOT}")
    print(f"Local gallery: {local_url}")
    print(f"LAN gallery:   {lan_url}")
    print(f"Local stream:  {streamer_local_url}")
    print(f"LAN stream:    {streamer_lan_url}")

    if not args.no_open:
        open_in_browser(local_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
