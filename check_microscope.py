#!/usr/bin/env python
"""
Check OpenFlexure Microscope Server availability.
Safe read-only check without executing any commands.
"""
import requests
import json
import sys

def check_microscope(server_url="http://192.168.3.58:5000"):
    """
    Check if OpenFlexure Microscope Server is available.
    
    Args:
        server_url: URL of the microscope server
        
    Returns:
        True if server is available, False otherwise
    """
    print(f"🔌 Checking OpenFlexure Microscope Server at {server_url}")
    print("=" * 60)
    
    try:
        # Проверка основного endpoint (WoT Thing Description)
        print("1. Checking /api/v2 endpoint (Thing Description)...")
        response = requests.get(f"{server_url}/api/v2", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Server is available")
            print(f"   Type: {data.get('@type', ['unknown'])[0] if data.get('@type') else 'unknown'}")
            print(f"   Actions: {len(data.get('actions', {}))} available")
            print(f"   Properties: {len(data.get('properties', {}))} available")
        else:
            print(f"   ⚠️  Server returned status {response.status_code}")
            return False
            
        # Проверка позиции через properties
        print("\n2. Checking /api/v2/properties/position endpoint...")
        response = requests.get(f"{server_url}/api/v2/properties/position", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Position property is available")
            print(f"   Position: {data}")
        else:
            print(f"   ⚠️  Could not get position (status {response.status_code})")
            
        # Проверка камеры через properties
        print("\n3. Checking /api/v2/properties/camera_settings endpoint...")
        response = requests.get(f"{server_url}/api/v2/properties/camera_settings", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Camera settings property is available")
            print(f"   Settings: {data}")
        else:
            print(f"   ⚠️  Could not get camera settings (status {response.status_code})")
            
        # Проверка захвата через actions
        print("\n4. Checking /api/v2/actions/CaptureAPI endpoint...")
        response = requests.get(f"{server_url}/api/v2/actions/CaptureAPI", timeout=5)
        
        if response.status_code == 200:
            print(f"   ✅ Capture action is available")
        else:
            print(f"   ⚠️  Capture action returned status {response.status_code}")
            
        print("\n" + "=" * 60)
        print("✅ Microscope server is available and ready!")
        return True
        
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Cannot connect to {server_url}")
        print(f"   Make sure the microscope server is running")
        return False
    except requests.exceptions.Timeout:
        print(f"   ❌ Connection timeout")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Check OpenFlexure Microscope Server availability")
    parser.add_argument("--url", default="http://localhost:5000", 
                       help="URL of the microscope server (default: http://localhost:5000)")
    
    args = parser.parse_args()
    
    if check_microscope(args.url):
        print("\n📝 Next steps:")
        print("   1. .env.local is already configured with microscope URL")
        print("   2. Run: python test_integration.py")
        print("   3. When ready, set MMSS_SAFETY_MODE_ACTIVE=False in .env.local")
        sys.exit(0)
    else:
        print("\n📝 Troubleshooting:")
        print("   - Make sure OpenFlexure Microscope Server is running")
        print("   - Check the URL is correct")
        print("   - Try: curl " + args.url + "/api/v2/about")
        sys.exit(1)

if __name__ == "__main__":
    main()
