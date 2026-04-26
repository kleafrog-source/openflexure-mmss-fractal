#!/usr/bin/env python
"""
Check OpenFlexure Microscope Server availability.
Safe read-only check without executing any commands.
"""
import requests
import json
import sys

def check_microscope(server_url="http://localhost:5000"):
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
        # Проверка основного endpoint
        print("1. Checking /api/v2/about endpoint...")
        response = requests.get(f"{server_url}/api/v2/about", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Server is available")
            print(f"   Version: {data.get('version', 'unknown')}")
            print(f"   API: {data.get('api', 'unknown')}")
        else:
            print(f"   ⚠️  Server returned status {response.status_code}")
            return False
            
        # Проверка статуса микроскопа
        print("\n2. Checking /api/v2/position endpoint...")
        response = requests.get(f"{server_url}/api/v2/position", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Microscope is connected")
            print(f"   Position: X={data.get('x', 0):.2f}, Y={data.get('y', 0):.2f}, Z={data.get('z', 0):.2f}")
        else:
            print(f"   ⚠️  Could not get position (status {response.status_code})")
            
        # Проверка возможностей
        print("\n3. Checking /api/v2/camera endpoint...")
        response = requests.get(f"{server_url}/api/v2/camera", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Camera is available")
            print(f"   Resolution: {data.get('width', 'unknown')}x{data.get('height', 'unknown')}")
        else:
            print(f"   ⚠️  Could not get camera info (status {response.status_code})")
            
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
        print("   1. Copy .env.example to .env.local")
        print("   2. Set USE_REAL_MICROSCOPE=False (for testing)")
        print("   3. Set MICROSCOPE_SERVER_URL=" + args.url)
        print("   4. Run: python test_integration.py")
        sys.exit(0)
    else:
        print("\n📝 Troubleshooting:")
        print("   - Make sure OpenFlexure Microscope Server is running")
        print("   - Check the URL is correct")
        print("   - Try: curl " + args.url + "/api/v2/about")
        sys.exit(1)

if __name__ == "__main__":
    main()
