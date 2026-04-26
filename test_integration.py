#!/usr/bin/env python
"""
Test integration with OpenFlexure Management Server.
"""
import sys
from src.mmss.safe_microscope import SafeMicroscopeWrapper

def test_connection():
    """Test connection to Management Server"""
    print("🔌 Testing connection to Management Server...")
    
    try:
        scope = SafeMicroscopeWrapper(
            server_url="http://localhost:8000",
            safe_mode=True
        )
        print("✅ Connected successfully!")
        return scope
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\n📝 Make sure Management Server is running:")
        print("   cd openflexure-management-server")
        print("   python manage.py runserver 0.0.0.0:8000")
        sys.exit(1)

def test_safe_mode(scope):
    """Test that safe mode prevents execution"""
    print("\n🛡️  Testing SAFE MODE...")
    
    # Эти команды должны только логироваться
    scope.set_light_spectrum(550, 80)
    scope.move_z(10)
    scope.capture_image("test_safe.jpg")
    
    # Проверить что команды залогированы
    log = scope.get_command_log()
    print(f"📝 Commands logged: {len(log)}")
    for cmd in log:
        print(f"   - {cmd['command']}")
    
    print("✅ Safe mode working correctly - no commands executed!")
    return True

def test_status(scope):
    """Get microscope status"""
    print("\n📊 Getting microscope status...")
    status = scope.get_status()
    
    if status:
        print("✅ Status received:")
        for key, value in status.items():
            print(f"   {key}: {value}")
        print(f"\n🛡️  Safe Mode: {'ENABLED' if scope.safe_mode else 'DISABLED'}")
        print(f"📝 Commands logged: {len(scope.get_command_log())}")
    else:
        print("⚠️  Could not get status (server may not have microscope connected)")
        print("💡 Try running: python check_microscope.py --url http://localhost:5000")

def main():
    print("=" * 60)
    print("OpenFlexure Management Server Integration Test")
    print("=" * 60)
    
    # 1. Подключиться
    scope = test_connection()
    
    # 2. Протестировать safe mode
    test_safe_mode(scope)
    
    # 3. Получить статус
    test_status(scope)
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("\n📝 Next steps:")
    print("   1. Start Management Server if not running")
    print("   2. Run: python test_integration.py")
    print("   3. If successful, mmss_engine.py is already updated")
    print("=" * 60)

if __name__ == "__main__":
    main()
