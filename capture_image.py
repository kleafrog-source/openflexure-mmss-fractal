#!/usr/bin/env python
"""
Capture image from OpenFlexure Microscope.
"""
import sys
import os
from dotenv import load_dotenv
from src.mmss.safe_microscope import SafeMicroscopeWrapper

# Load environment variables
load_dotenv('.env.local')

def capture_image(filename="microscope_capture.jpg"):
    """Capture image from microscope"""
    print("📸 Capturing image from microscope...")
    
    server_url = os.getenv('MICROSCOPE_SERVER_URL', 'http://localhost:5000')
    
    try:
        # Подключиться с отключенным safe mode для реального захвата
        scope = SafeMicroscopeWrapper(
            server_url=server_url,
            safe_mode=False  # Отключаем safe mode для реального захвата
        )
        
        print(f"🔌 Connected to {server_url}")
        print(f"⚠️  Safe mode DISABLED - real capture will be performed")
        
        # Захватить изображение
        image_path = scope.capture_image(filename=filename)
        
        if image_path:
            print(f"✅ Image saved to: {image_path}")
            return image_path
        else:
            print("❌ Failed to capture image")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Capture image from OpenFlexure Microscope")
    parser.add_argument("--filename", default="microscope_capture.jpg", 
                       help="Output filename (default: microscope_capture.jpg)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("OpenFlexure Microscope Image Capture")
    print("=" * 60)
    
    image_path = capture_image(args.filename)
    
    if image_path:
        print("\n" + "=" * 60)
        print("✅ Capture successful!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ Capture failed")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
