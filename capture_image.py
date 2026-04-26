#!/usr/bin/env python
"""
Capture an image from the OpenFlexure microscope and optionally analyze it.
"""
import argparse
import datetime
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
from src.mmss.safe_microscope import SafeMicroscopeWrapper


load_dotenv(".env.local")


def build_capture_filename(filename: str | None = None) -> str:
    """Build a unique capture filename when one is not provided."""
    if filename:
        return filename

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"microscope_capture_{timestamp}.jpg"


def prepare_capture_target(filename: str | None = None) -> tuple[str, str]:
    """Prepare a session folder and a relative target path under output/."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = Path(build_capture_filename(filename)).name
    session_id = f"{timestamp}_{Path(base_name).stem}"
    relative_path = Path("sessions") / session_id / base_name
    return session_id, relative_path.as_posix()


def capture_image(filename: str | None = None) -> str | None:
    """Capture an image from the microscope."""
    print("Capturing image from microscope...")

    server_url = os.getenv("MICROSCOPE_SERVER_URL", "http://localhost:5000")
    session_id, filename = prepare_capture_target(filename)

    try:
        scope = SafeMicroscopeWrapper(
            server_url=server_url,
            safe_mode=False,
        )

        print(f"Connected to {server_url}")
        print("Safe mode DISABLED - real capture will be performed")

        image_path = scope.capture_image(filename=filename)
        if image_path:
            print(f"Image saved to: {image_path}")
            print(f"Session folder: output/sessions/{session_id}")
            return image_path

        print("Failed to capture image")
        return None
    except Exception as exc:
        print(f"Error: {exc}")
        return None


def run_fractal_analysis(image_path: str, analysis_mode: str = "invariants"):
    """Run MMSS fractal analysis for the captured image."""
    print("\nStarting fractal analysis...")

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
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Capture an image from the OpenFlexure microscope"
    )
    parser.add_argument(
        "--filename",
        default=None,
        help="Output filename. If omitted, a timestamped filename is generated.",
    )
    parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Only capture the image and skip automatic fractal analysis.",
    )
    parser.add_argument(
        "--analysis-mode",
        default="invariants",
        choices=["invariants", "hybrid", "vision_only"],
        help="Analysis mode: invariants only, hybrid invariants+Mistral vision, or Mistral-led vision_only.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("OpenFlexure Microscope Image Capture")
    print("=" * 60)

    image_path = capture_image(args.filename)

    if not image_path:
        print("\n" + "=" * 60)
        print("Capture failed")
        print("=" * 60)
        sys.exit(1)

    analysis_results = None
    published_view = None
    if not args.no_analyze:
        analysis_results = run_fractal_analysis(image_path, analysis_mode=args.analysis_mode)
        if analysis_results:
            published_view = publish_analysis_view(image_path, analysis_results)

    print("\n" + "=" * 60)
    print("Capture successful!")
    print(f"Saved image: {image_path}")
    if analysis_results:
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
