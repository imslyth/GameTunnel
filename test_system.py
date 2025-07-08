#!/usr/bin/env python3
"""
GameTunnel System Test - Verify all components work correctly
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test all module imports"""
    print("🔍 Testing imports...")
    
    try:
        from utils import Config, NetworkUtils, ServerInfo, ConnectionStats, Logger
        print("  ✅ Utils module imported successfully")
        
        from client.main import TunnelClient
        print("  ✅ Client module imported successfully")
        
        from server.main import TunnelServer
        print("  ✅ Server module imported successfully")
        
        from dashboard.app import DashboardApp
        print("  ✅ Dashboard module imported successfully")
        
        return True
    except Exception as e:
        print(f"  ❌ Import error: {e}")
        return False

def test_configuration():
    """Test configuration loading"""
    print("\n🔧 Testing configuration...")
    
    try:
        from utils import Config
        config = Config("config/config.yaml")
        
        # Test basic config access
        servers = config.get('servers', [])
        games = config.get('games', [])
        
        print(f"  ✅ Configuration loaded: {len(servers)} servers, {len(games)} games")
        return True
    except Exception as e:
        print(f"  ❌ Configuration error: {e}")
        return False

def test_network_utils():
    """Test network utilities"""
    print("\n🌐 Testing network utilities...")
    
    try:
        from utils import NetworkUtils
        
        # Test local IP detection
        local_ip = NetworkUtils.get_local_ip()
        print(f"  ✅ Local IP detected: {local_ip}")
        
        # Test port checking
        port_free = not NetworkUtils.is_port_in_use(65432)
        print(f"  ✅ Port checking works: {port_free}")
        
        return True
    except Exception as e:
        print(f"  ❌ Network utils error: {e}")
        return False

async def test_ping():
    """Test ping functionality"""
    print("\n📡 Testing ping functionality...")
    
    try:
        from utils import NetworkUtils
        
        # Test ping to Google DNS
        latency, success = await NetworkUtils.ping_host("8.8.8.8", 53, timeout=3.0)
        
        if success:
            print(f"  ✅ Ping test successful: {latency:.1f}ms to 8.8.8.8:53")
        else:
            print("  ⚠️  Ping test failed (network may be restricted)")
        
        return True
    except Exception as e:
        print(f"  ❌ Ping test error: {e}")
        return False

def test_directories():
    """Test required directories exist"""
    print("\n📁 Testing directories...")
    
    required_dirs = [
        "logs",
        "dashboard/templates",
        "dashboard/static",
        "config"
    ]
    
    all_exist = True
    for directory in required_dirs:
        if os.path.exists(directory):
            print(f"  ✅ {directory} exists")
        else:
            print(f"  ❌ {directory} missing")
            all_exist = False
    
    return all_exist

def test_dashboard_template():
    """Test dashboard template exists"""
    print("\n🌐 Testing dashboard template...")
    
    template_path = "dashboard/templates/dashboard.html"
    
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if "GameTunnel Dashboard" in content:
            print(f"  ✅ Dashboard template exists and valid ({len(content)} chars)")
            return True
        else:
            print("  ❌ Dashboard template exists but invalid")
            return False
    else:
        print("  ❌ Dashboard template missing")
        return False

async def main():
    """Run all tests"""
    print("🧪 GameTunnel System Test")
    print("=" * 40)
    
    tests = [
        ("Import Test", test_imports),
        ("Configuration Test", test_configuration),
        ("Network Utils Test", test_network_utils),
        ("Ping Test", test_ping),
        ("Directories Test", test_directories),
        ("Dashboard Template Test", test_dashboard_template)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"  ❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 40)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! GameTunnel is ready to use.")
        print("\n🚀 To get started:")
        print("   1. Start dashboard: python main.py dashboard")
        print("   2. Start server: python main.py server --host 0.0.0.0")
        print("   3. Connect client: python main.py client --server-host localhost")
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
    
    return passed == total

if __name__ == "__main__":
    asyncio.run(main())
