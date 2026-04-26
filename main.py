#!/usr/bin/env python3
"""
Main entry point for the MMSS-Alpha-Formula (v2.0) application.
"""
import argparse
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.append(str(Path(__file__).parent / 'src'))

from mmss.mmss_engine import MMSS_Engine
from mmss.report_publisher import (
    build_viewer_targets,
    ensure_report_server,
    open_in_browser,
    publish_analysis_session,
)

def main():
    """
    Main function to run the MMSS-Alpha-Formula application.
    """
    parser = argparse.ArgumentParser(description="Run MMSS analysis on an image")
    parser.add_argument("image_path", help="Path to the image file")
    parser.add_argument(
        "--analysis-mode",
        default="invariants",
        choices=["invariants", "hybrid", "vision_only"],
        help="Analysis mode: invariants only, hybrid invariants+Mistral vision, or Mistral-led vision_only.",
    )
    args = parser.parse_args()

    os.environ["MMSS_ANALYSIS_MODE"] = args.analysis_mode
    image_path = args.image_path
    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}")
        sys.exit(1)

    try:
        # The new engine does not require a config file in the same way,
        # but we could load one here if needed in the future.
        config = {}
        engine = MMSS_Engine(config)
        
        # Run the analysis with the provided image
        # The engine.run() method now handles saving the report file
        # and returns the results dictionary
        results = engine.run(image_path)
        
        # The report path is already included in the results
        report_path = results.get('report_path', 'output/reports/unknown_report.json')
        print(f"\nAnalysis complete! Report saved to: {report_path}")

        published = publish_analysis_session(image_path, results)
        print(f"Session viewer saved to: {published['viewer_path']}")

        server_url = ensure_report_server()
        if server_url:
            viewer_urls = build_viewer_targets(published["session_id"])
            print(f"Browser viewer: {viewer_urls['local_url']}")
            print(f"LAN viewer: {viewer_urls['lan_url']}")
            print(f"Result streamer: {viewer_urls['result_streamer_local_url']}")
            print(f"Result streamer LAN: {viewer_urls['result_streamer_lan_url']}")
            open_in_browser(viewer_urls["local_url"])
        else:
            file_url = Path(published["viewer_path"]).resolve().as_uri()
            print(f"Browser viewer: {file_url}")
            open_in_browser(file_url)
        
        # Return the results for potential further processing
        return results
        
    except Exception as e:
        print(f"Error during execution: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
