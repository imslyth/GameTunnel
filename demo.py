#!/usr/bin/env python3
"""
GameTunnel Demo - Demonstrates the network tunneling capabilities
"""

import asyncio
import logging
import time
from utils import Config, NetworkUtils, ServerInfo, Logger

async def demo_ping_servers():
    """Demo: Test connectivity to various servers"""
    print("🚀 GameTunnel Demo - Network Optimization")
    print("=" * 50)
    
    # Load configuration
    config = Config("config/config.yaml")
    Logger.setup_logging(config)
    
    # Get servers from config
    servers = config.get('servers', [])
    
    print(f"\n📡 Testing {len(servers)} servers for optimal routing...\n")
    
    results = []
    
    for server_config in servers:
        server = ServerInfo(
            name=server_config['name'],
            host=server_config['host'],
            port=server_config['port'],
            region=server_config['region'],
            location=server_config['location']
        )
        
        print(f"🔍 Testing {server.name} ({server.location})...")
        
        # Test server with multiple pings
        latencies = []
        for i in range(3):
            latency, success = await NetworkUtils.ping_host(
                server.host, server.port, timeout=5.0
            )
            
            if success:
                latencies.append(latency)
                print(f"   Ping {i+1}: {latency:.1f}ms ✅")
            else:
                print(f"   Ping {i+1}: TIMEOUT ❌")
            
            await asyncio.sleep(0.5)
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            server.latency = avg_latency
            results.append(server)
            print(f"   Average: {avg_latency:.1f}ms\n")
        else:
            print(f"   Server unreachable\n")
    
    # Show results
    if results:
        print("📊 Server Performance Results:")
        print("-" * 50)
        results.sort(key=lambda s: s.latency)
        
        for i, server in enumerate(results, 1):
            status = "🟢 EXCELLENT" if server.latency < 50 else \
                    "🟡 GOOD" if server.latency < 100 else \
                    "🟠 FAIR" if server.latency < 200 else "🔴 POOR"
            
            print(f"{i}. {server.name:<15} {server.latency:>6.1f}ms  {status}")
        
        best_server = results[0]
        print(f"\n🎯 Recommended server: {best_server.name}")
        print(f"   Location: {best_server.location}")
        print(f"   Latency: {best_server.latency:.1f}ms")
        
        # Calculate potential improvement
        worst_latency = max(s.latency for s in results)
        improvement = worst_latency - best_server.latency
        
        if improvement > 10:
            print(f"   💡 Potential improvement: -{improvement:.1f}ms compared to worst server")
    
    else:
        print("❌ No servers are currently available")

def demo_game_optimization():
    """Demo: Show game-specific optimizations"""
    print("\n🎮 Game-Specific Optimizations:")
    print("-" * 50)
    
    config = Config("config/config.yaml")
    games = config.get('games', [])
    
    for game in games:
        print(f"🕹️  {game['name']}")
        print(f"   Executable: {game['executable']}")
        print(f"   Ports: {', '.join(map(str, game['ports']))}")
        print(f"   Protocol: {game['protocol'].upper()}")
        print(f"   Optimization: {game['optimization']}")
        print()

def show_architecture():
    """Show the GameTunnel architecture"""
    print("\n🏗️  GameTunnel Architecture:")
    print("-" * 50)
    print("""
    Game Client ←→ Tunnel Client ←→ Tunnel Server ←→ Game Server
                         ↓
                    Web Dashboard
    
    How it works:
    1. Game traffic is intercepted by the Tunnel Client
    2. Traffic is routed through the optimal Tunnel Server
    3. Server forwards traffic to the actual Game Server
    4. Response follows the same path back
    5. Dashboard monitors performance in real-time
    """)

def show_usage_examples():
    """Show usage examples"""
    print("\n📚 Usage Examples:")
    print("-" * 50)
    print("""
    Start a tunnel server:
    python main.py server --host 0.0.0.0 --port 8080 --region us-east
    
    Connect tunnel client:
    python main.py client --server-host your-server.com --server-port 8080
    
    Launch web dashboard:
    python main.py dashboard --host 127.0.0.1 --port 5000
    
    Test server connectivity:
    python demo.py
    """)

async def main():
    """Main demo function"""
    try:
        show_architecture()
        demo_game_optimization()
        show_usage_examples()
        await demo_ping_servers()
        
        print("\n✅ Demo completed!")
        print("🔧 Edit config/config.yaml to customize your setup")
        print("📖 See README.md for detailed documentation")
        
    except Exception as e:
        print(f"❌ Demo error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
