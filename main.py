#!/usr/bin/env python3
"""
Main entry point for the MMSS-Alpha-Formula (v2.0) application.
"""
import json
import os
import sys
import datetime
from pathlib import Path

# Add the src directory to the Python path
sys.path.append(str(Path(__file__).parent / 'src'))

from mmss.mmss_engine import MMSS_Engine

def main():
    """
    Main function to run the MMSS-Alpha-Formula application.
    """
    if len(sys.argv) < 2:
        print("Usage: python main.py <image_path>")
        sys.exit(1)
    
    image_path = sys.argv[1]
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
        
        # Return the results for potential further processing
        return results
        
    except Exception as e:
        print(f"Error during execution: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
