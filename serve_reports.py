#!/usr/bin/env python
"""
Serve generated MMSS reports over HTTP for browser-based viewing.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

from src.mmss.report_publisher import OUTPUT_ROOT, SESSIONS_ROOT, build_gallery, get_local_ip, open_in_browser

load_dotenv(".env.local")


class APIHandler(SimpleHTTPRequestHandler):
    """Custom handler that serves static files and API endpoints."""
    
    def do_POST(self):
        """Handle POST requests for API endpoints."""
        if self.path == "/api/batch-analysis":
            self.handle_batch_analysis()
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
            image_path = manifest.get("image_path")
            report_path = manifest.get("report_path")
            
            if not image_path or not Path(image_path).exists():
                self.send_error(404, "Image not found")
                return
            
            # Run analysis based on mode
            from src.mmss.mmss_engine import MMSS_Engine
            
            os.environ["USE_REAL_MICROSCOPE"] = "False"
            os.environ["MMSS_SAFETY_MODE_ACTIVE"] = "True"
            os.environ["MMSS_ANALYSIS_MODE"] = mode
            
            engine = MMSS_Engine(config={})
            
            if mode == "vision_only":
                # Single vision call
                vision_result = engine._analyze_raw_image_with_mistral(image_path)
                if not vision_result:
                    time.sleep(5)
                    vision_result = engine._analyze_raw_image_with_mistral(image_path)
                analysis_result = {"vision_analysis": vision_result}
            else:
                # Full analysis for invariants/hybrid
                analysis_result = engine.run(image_path)
            
            # Update report with mode-specific block
            if report_path and Path(report_path).exists():
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)
                
                # Store result in mode-specific block
                if mode == "invariants":
                    report["invariants_analysis"] = analysis_result
                    manifest["has_invariants"] = True
                elif mode == "hybrid":
                    report["hybrid_analysis"] = analysis_result
                    manifest["has_hybrid"] = True
                elif mode == "vision_only":
                    report["vision_only_analysis"] = analysis_result
                    manifest["has_vision_only"] = True
                
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False, default=str)
                
                # Update manifest
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            
            # Rebuild gallery to update status
            build_gallery()
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"success": True, "mode": mode, "result": analysis_result}
            self.wfile.write(json.dumps(response).encode("utf-8"))
            
        except Exception as e:
            print(f"Error in batch analysis: {e}")
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
