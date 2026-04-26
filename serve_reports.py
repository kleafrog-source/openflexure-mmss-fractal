#!/usr/bin/env python
"""
Serve generated MMSS reports over HTTP for browser-based viewing.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.mmss.report_publisher import OUTPUT_ROOT, build_gallery, get_local_ip, open_in_browser


def main():
    parser = argparse.ArgumentParser(description="Serve MMSS report gallery over HTTP")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8765, help="TCP port to serve")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()

    build_gallery()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(OUTPUT_ROOT)))
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
