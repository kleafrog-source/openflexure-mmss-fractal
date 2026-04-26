#!/usr/bin/env python
"""
Analyze a previously captured image with MMSS fractal analysis.
Useful when you need to capture without VPN and analyze with VPN enabled.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.mmss.mmss_engine import MMSS_Engine
from src.mmss.report_publisher import (
    build_viewer_targets,
    ensure_report_server,
    open_in_browser,
    publish_analysis_session,
)


load_dotenv(".env.local")


def run_fractal_analysis(image_path: str, analysis_mode: str = "invariants"):
    """Run MMSS fractal analysis for the captured image."""
    print(f"\nStarting fractal analysis for: {image_path}")
    print(f"Analysis mode: {analysis_mode}")

    previous_use_real = os.environ.get("USE_REAL_MICROSCOPE")
    previous_safety_mode = os.environ.get("MMSS_SAFETY_MODE_ACTIVE")
    previous_analysis_mode = os.environ.get("MMSS_ANALYSIS_MODE")

    try:
        # Analysis of an already captured frame does not need live microscope access.
        os.environ["USE_REAL_MICROSCOPE"] = "False"
        os.environ["MMSS_SAFETY_MODE_ACTIVE"] = "True"
        os.environ["MMSS_ANALYSIS_MODE"] = analysis_mode

        engine = MMSS_Engine(config={})
        results = engine.run(image_path)
        report_path = results.get("report_path", "output/reports/unknown_report.json")
        print(f"Fractal analysis complete! Report saved to: {report_path}")
        return results
    except Exception as exc:
        print(f"Fractal analysis failed: {exc}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if previous_use_real is None:
            os.environ.pop("USE_REAL_MICROSCOPE", None)
        else:
            os.environ["USE_REAL_MICROSCOPE"] = previous_use_real

        if previous_safety_mode is None:
            os.environ.pop("MMSS_SAFETY_MODE_ACTIVE", None)
        else:
            os.environ["MMSS_SAFETY_MODE_ACTIVE"] = previous_safety_mode

        if previous_analysis_mode is None:
            os.environ.pop("MMSS_ANALYSIS_MODE", None)
        else:
            os.environ["MMSS_ANALYSIS_MODE"] = previous_analysis_mode


def publish_analysis_view(image_path: str, analysis_results: dict) -> dict | None:
    """Bundle image, JSON report, and HTML viewer into one session."""
    try:
        published = publish_analysis_session(image_path, analysis_results)
        print(f"Session viewer saved to: {published['viewer_path']}")

        server_url = ensure_report_server()
        if server_url:
            viewer_urls = build_viewer_targets(published["session_id"])
            print(f"Browser viewer: {viewer_urls['local_url']}")
            print(f"LAN viewer: {viewer_urls['lan_url']}")
            print(f"Result streamer: {viewer_urls['result_streamer_local_url']}")
            print(f"Result streamer LAN: {viewer_urls['result_streamer_lan_url']}")
            open_in_browser(viewer_urls["local_url"])
            published.update(viewer_urls)
        else:
            file_url = Path(published["viewer_path"]).resolve().as_uri()
            print(f"Browser viewer: {file_url}")
            open_in_browser(file_url)
            published["local_file_url"] = file_url

        return published
    except Exception as exc:
        print(f"Failed to publish browser view: {exc}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a previously captured image with MMSS fractal analysis"
    )
    parser.add_argument(
        "image_path",
        help="Path to the image file to analyze",
    )
    parser.add_argument(
        "--analysis-mode",
        default="invariants",
        choices=["invariants", "hybrid", "vision_only"],
        help="Analysis mode: invariants only, hybrid invariants+Mistral vision, or Mistral-led vision_only.",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Only analyze the image and skip publishing to web viewer.",
    )
    args = parser.parse_args()

    # Validate image path
    image_path = Path(args.image_path)
    if not image_path.exists():
        print(f"Error: Image file not found: {args.image_path}")
        sys.exit(1)

    print("=" * 60)
    print("MMSS Fractal Image Analysis")
    print("=" * 60)

    analysis_results = run_fractal_analysis(str(image_path), analysis_mode=args.analysis_mode)

    if not analysis_results:
        print("\n" + "=" * 60)
        print("Analysis failed")
        print("=" * 60)
        sys.exit(1)

    published_view = None
    if not args.no_publish:
        published_view = publish_analysis_view(str(image_path), analysis_results)

    print("\n" + "=" * 60)
    print("Analysis successful!")
    print(f"Image: {image_path}")
    print(f"Analysis report: {analysis_results.get('report_path')}")
    if published_view:
        print(f"Session report folder: {published_view.get('session_dir')}")
        if published_view.get("local_url"):
            print(f"Open in browser: {published_view['local_url']}")
        if published_view.get("result_streamer_local_url"):
            print(f"Stable streamer URL: {published_view['result_streamer_local_url']}")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
